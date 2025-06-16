import grpc
import myitems_pb2 as pb2
import myitems_pb2_grpc as pb2_grpc
import logging
import time
import os



logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run():
    channel = grpc.insecure_channel("localhost:50051", options=(('grpc.enable_http_proxy', 0),))
    logging.info("Connecting to gRPC server at localhost:50051")
    stub = pb2_grpc.ItemServiceStub(channel)
    
    # 1. Client-streaming
    # Create an iterator of ItemRequest messages
    # Then call stub.AddItems(...) and capture the final result
    names = ["Moodle", "Student Services", "WebUntis", " Student Mail"]

    def name_generator():
        for name in names:
            yield pb2.ItemName(name=name)

    response = stub.AddItems(name_generator())
    logging.info("Client-streaming response: %s", response)

    # Print the total count of items added
    logging.info("Client-streaming response. The new items count is: %d", response.total_count)

    # 2. Unary
    # Call stub.GetItemById() with an ItemRequest and print the response
    logging.info("Calling GetItemById with id=1")
    response = stub.GetItemById(pb2.ItemRequest(id=1))
    logging.info("Unary response: %s", response)

    # 3. Server-streaming
    # Call stub.ListAllItems() and print the responses
    for item in stub.ListAllItems(pb2.Empty()):
        logging.info("Server-streaming item: %s", item)


    # 4. Bidirectional
    # Open a stub.ChatAboutItems() stream
    # Send ChatMessage objects and read responses in a loop
    def chat_generator():
        logging.info("Starting bidirectional chat stream")
        for name in names:
            print("Sending chat message:", name)
            # Create a ChatMessage object and send it
            yield pb2.ChatMessage(content=f"Hello from {name}")
    # Call stub.ChatAboutItems() and print the responses
    response = stub.ChatAboutItems(chat_generator())
    for message in response:
        logging.info("Bidirectional response: %s", message.content)
  
    # 5. Error handling


if __name__ == "__main__":
    run()
