from flask import Flask, jsonify, request
import time, random, logging, os, grpc, threading, queue
from pybreaker import CircuitBreaker, CircuitBreakerError
from grpc_health.v1 import health_pb2, health_pb2_grpc

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
        stub = get_grpc_stub()
        response = stub.Check(health_pb2.HealthCheckRequest(service=''), timeout=1)
        logging.info(f'gRPC Health check result: {response.status}')
        return response.status == health_pb2.HealthCheckResponse.SERVING
    except Exception:
        return False

# In-memory queue for failed add item requests
failed_requests_queue = queue.Queue()

def retry_failed_requests():
    while True:
        item = failed_requests_queue.get()
        if item is None:
            break  # Allows for clean shutdown if needed
        else:
            if is_grpc_healthy():
                try:
                    logging.info("Background retry thread started")
                    # Try to add the item again using the circuit breaker
                    response = breaker.call(grpc_create, item)
                    logging.info(f"Retried item added successfully: {item}")
                except Exception as e:
                    logging.error(f"Retry failed for item {item}: {e}")
                    # Put it back in the queue to try again later
                    failed_requests_queue.put(item)
                    # Wait before retrying to avoid tight loop
                    time.sleep(5)
                finally:
                    failed_requests_queue.task_done()

# Start the background worker thread
worker_thread = threading.Thread(target=retry_failed_requests, daemon=True)
worker_thread.start()


@app.route('/items')
def get_items():
    try:
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
    except CircuitBreakerError:
        logging.warning('Circuit breaker open on GET /items')
        return jsonify({"error": "Service temporarily unavailable"}), 503
    except grpc.RpcError:
        logging.error('gRPC call to list items failed')
        return jsonify({"error": "Backend unavailable"}), 503
    return jsonify(items)


@app.route('/items', methods=['POST'])
def add_item():
    logging.info('Adding a new item')
    # item_name = request.get_json()['name']
    item = request.get_json() 
    delay = 0.1 # first retry back-off (100 ms)

    for attempt in range(3):
        try:
            response = breaker.call(grpc_create, item)
            return {"message": "Item created", "added": response.total_count}, 201
        except CircuitBreakerError:
            failed_requests_queue.put(item)
            return {"error": "Service is currently unavailable. Please try again later."}, 503
        except grpc.RpcError:
            logging.error(f'Attempt {attempt + 1}: gRPC call failed')
            if attempt == 2:
                failed_requests_queue.put(item)
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
    app.run(debug=True, host='0.0.0.0', port=5000)
