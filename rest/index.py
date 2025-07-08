from flask import Flask, jsonify, request
import time, logging, os, grpc, threading
from pybreaker import CircuitBreaker, CircuitBreakerError
from grpc_health.v1 import health_pb2, health_pb2_grpc
from prometheus_client import Counter, Histogram, generate_latest

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Request Latency",
    ["method", "endpoint"]
)

REQUEST_COUNTER = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"])

breaker = CircuitBreaker(fail_max=3, reset_timeout=30)

import myitems_pb2 as pb2
import myitems_pb2_grpc as pb2_grpc

GRPC_HOST = os.getenv('GRPC_HOST', 'localhost')
GRPC_PORT = os.getenv('GRPC_PORT', '50051')


app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# create  a new stub each time to ensure it uses the latest channel
# This is useful if the gRPC server might restart or change
# and we want to avoid using a stale channel.
def get_grpc_stub():
    channel = grpc.insecure_channel(f'{GRPC_HOST}:{GRPC_PORT}', options=(('grpc.enable_http_proxy', 0),))
    return pb2_grpc.ItemServiceStub(channel)

def grpc_create(item):
    stub = get_grpc_stub()
    req = pb2.ItemName(name=item["name"])
    return stub.AddItem(req, timeout=1)


#check if gRPC service is healthy 
def is_grpc_healthy():
    try:
        channel = grpc.insecure_channel(f'{GRPC_HOST}:{GRPC_PORT}', options=(('grpc.enable_http_proxy', 0),))
        health_stub = health_pb2_grpc.HealthStub(channel)
        response = health_stub.Check(health_pb2.HealthCheckRequest(service=''), timeout=1)
        return response.status == health_pb2.HealthCheckResponse.SERVING
    except Exception:
        return False

# function to check the health of the gRPC service and control the circuit breaker
def health_check():
    while True:
        health_status = is_grpc_healthy()
        logging.info(f'Current breaker state: {breaker.current_state}')

        if health_status:
            if breaker.current_state == 'open':
                logging.info('gRPC service is healthy, closing the circuit breaker')
                breaker.close()
            # Optionally, you can reset the breaker if it was open
        else:
            if breaker.current_state == 'closed':
                logging.warning('gRPC service is unhealthy, opening the circuit breaker')
                breaker.open()
        time.sleep(2)  # Check every 2 seconds

# starts a timer for each request
@app.before_request
def _start_timer():
    # returns a stop function bound to the request
    request._start_time = time.time()
    
# after the request is processed, this stops the timer and  record the request duration
# and increment the request counter
@app.after_request
def _after(response):
    resp_time = time.time() - request._start_time
    REQUEST_LATENCY.labels(request.method, request.path).observe(resp_time)
    REQUEST_COUNTER.labels(
        request.method, request.path, response.status_code).inc()
    return response
@app.route('/metrics')
def metrics():
    logging.info('Fetching metrics')
    # Return the Prometheus metrics
    return generate_latest(), 200, {'Content-Type': 'text/plain; version=0.0.4'}   
        
@app.route('/items')
def get_items():

    logging.info('Fetching all items')
    # Make the gRPC call to list all items
    stub = get_grpc_stub()
    response = stub.ListAllItems(pb2.Empty())
    items = []
    for item in response:
        items.append({"id": item.id, "name": item.name})
    logging.info(f'Items fetched: {items}')
    # Return the items as JSON
    logging.info('Returning items as JSON response')
    return jsonify(items)


@app.route('/items', methods=['POST'])
def add_item():
    # Check if the gRPC service is healthy before proceeding
    if breaker.current_state == 'open' or not is_grpc_healthy():
        logging.warning('Circuit breaker is open or gRPC service is unhealthy')
        return {"error": "Service is currently unavailable. Please try again later."}, 503
    # check state of the circuit breaker before proceeding
    logging.info('Adding a new item')
    # item_name = request.get_json()['name']
    item = request.get_json() 
    delay = 0.1 # first retry back-off (100 ms)

    for attempt in range(3):
        try:
            response = breaker.call(grpc_create, item)
            return {"message": "Item created", "added": response.total_count}, 201
        except CircuitBreakerError:     
            #open the circuit breaker
            breaker.open()   
            # return a 503 Service Unavailable response
            return {"error": "Service is currently unavailable. Please try again later."}, 503
        except grpc.RpcError:
            logging.error(f'Attempt {attempt + 1}: gRPC call failed')
            if attempt == 2:
                logging.error('Failed to add item after 3 attempts')
                break
        time.sleep(delay)
        delay *= 2  # Exponential back-off

    return {"error": "backend_failure"}, 500


@app.route('/items/<int:id>', methods=['GET'])
def get_item(id):
    stub = get_grpc_stub()
    logging.info(f'Fetching item with id: {id}')
    response = stub.GetItemById(pb2.ItemRequest(id=1))
    return jsonify({"id": response.id, "name": response.name}), 200
  


if __name__ == "__main__":
    logging.info('Starting the Flask application')
    # Only start the health check thread in the main process (not the reloader)
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        health_thread = threading.Thread(target=health_check, name='Health check thread', daemon=True)
        health_thread.start()
    app.run(debug=True, host='0.0.0.0', port=5000)
