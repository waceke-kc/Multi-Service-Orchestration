### Docker Compose & Reliability lab

#### Container setup
In order to set up the containers, just ensure that you are withing the main folder and then run the command  to build the containers and run them in the background

    docker compose up -d


#### Verification 

You can verify that the containers are working correcctly by running the following commands

    grpcurl -plaintext localhost:50051 list myitems.ItemService

to see that the GPRC container is up

    curl   'http://localhost:5000/items'  

to check the rest container and 

     docker exec -it mongodb mongosh

to log into the mongodb container shell and see the collection. Or you can use whatever other mean work for you. 


Useful commands

- docker ps --format 'table {{.Names}}     {{.Status}}     {{.Ports}}'
