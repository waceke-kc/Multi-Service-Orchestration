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
    logging.info('Adding a new item')
    # item_name = request.get_json()['name']
    item = request.get_json() 
    delay = 0.1 # first retry back-off (100 ms)

    for attempt in range(3):
        try:
            response = breaker.call(grpc_create, item)
            return {"message": "Item created", "added": response.total_count}, 201
        except CircuitBreakerError:
           
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
    app.run(debug=True, host='0.0.0.0', port=5000)
