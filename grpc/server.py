import grpc
#add grpc_reflection
from grpc_reflection.v1alpha import reflection
from grpc_health.v1 import health, health_pb2_grpc, health_pb2
from concurrent import futures
from pymongo import MongoClient
import os
import myitems_pb2 as pb2
import myitems_pb2_grpc as pb2_grpc
import time
import logging

# Configurations for better code readability
ENABLE_LOGGING_INTERCEPTOR = False
ENABLE_REFLECTION = True

# MongoDB connection
mongo_host = os.getenv("MONGO_HOST", "localhost")
mongo_port = os.getenv("MONGO_PORT", "27017")

mongo_db = os.getenv("MONGO_DB", "itemsdb")
try:
    client = MongoClient(f"mongodb://{mongo_host}:{mongo_port}", serverSelectionTimeoutMS=5000)
    client.admin.command('ping')  # Force connection
    db = client[mongo_db]
    collection = db["items"]
    collection.create_index("id", unique=True)
    logging.info("Connected to MongoDB successfully.")
except Exception as e:
    logging.error(f"Failed to connect to MongoDB: {e}")
    raise e


## use logging instead of print
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ItemServiceServicer(pb2_grpc.ItemServiceServicer):

    #Unary
    def GetItemById(self, request, context):   
        logging.info(f"*** GetItemById called for id: {request.id}\n")
        doc = collection.find_one({"id": request.id})
        if not doc:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            logging.error(f"Item with id {request.id} not found")
            context.set_details(f"Item with id {request.id} not found")
            return pb2.ItemResponse()
        return pb2.ItemResponse(id=doc["id"], name=doc["name"])
    # Unary
    def AddItem(self, request, context):
        logging.info(f"*** AddItem called with name: {request.name}\n")
        
        # Get the last id from the existing items
        items = list(collection.find())
        if items:
            last_id = max(item["id"] for item in items)
        else:
            last_id = 0 
        count = len(items)
        logging.info(f"Last item id in the database is: {last_id}")
        # Create a new item
        new_item = {'id': last_id + 1, 'name': request.name}    
        collection.insert_one(new_item)  # Insert new item into MongoDB
        count += 1
        logging.info(f"New item added. Total count is now: {count}")
        return pb2.ItemsCount(total_count=count)
     
    # Server Streaming
    def ListAllItems(self, request, context):
        logging.info("*** ListAllItems called\n")
        items = list(collection.find())  # Fetch all items from MongoDB
        for item in items: 
          yield pb2.ItemResponse(id=item["id"], name=item["name"])

    # Client Streaming
    def AddItems(self, request_iterator, context): 
        logging.info("*** AddItems called\n")
        # add items to MongoDB
        items = list(collection.find())  # Fetch all items from MongoDB
        # get the last id from the existing items
        if items:
            last_id = max(item["id"] for item in items)
        else:
            last_id = 0
        logging.info(f"Last item id in the database is: {last_id}")
        # Initialize count   
        count = len(items)
        for item in request_iterator:
            new_item =  {'id': last_id + 1, 'name': item.name}
            collection.insert_one(new_item)  # Insert new item into MongoDB
           
            count += 1
            last_id += 1
            logging.info(f"New item added. Total count is now: {count}")
        return pb2.ItemsCount(total_count = count)
    # Bidirectional Streaming

    def ChatAboutItems(self, request_iterator, context):
        for message in request_iterator:
           reply= f"Your message was: { message.content}"
           yield pb2.ChatMessage(content=reply)

class LoggingInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, handler_call_details):
        method = handler_call_details.method
        metadata = handler_call_details.invocation_metadata
        logging.info(f"[gRPC LOG] Method: {method}, Metadata: {metadata}")
        return continuation(handler_call_details) # meaning gRPC can be continued

def serve():
    interceptors = [LoggingInterceptor()] if ENABLE_LOGGING_INTERCEPTOR else []
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=interceptors
    )

    logging.info("Starting gRPC server...")
    pb2_grpc.add_ItemServiceServicer_to_server(
        ItemServiceServicer(),
        server
    )
    # Add health checking service
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set('', health_pb2.HealthCheckResponse.SERVING)

    if ENABLE_REFLECTION:
        logging.info("Enabling gRPC reflection...")
        SERVICE_NAMES = (
            pb2.DESCRIPTOR.services_by_name['ItemService'].full_name,
            reflection.SERVICE_NAME,
        )
        reflection.enable_server_reflection(SERVICE_NAMES, server)
   
    server.add_insecure_port('[::]:50051')
    server.start()
    logging.info(f"*** gRPC server started with default items loaded. Listening on port 50051\n")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()