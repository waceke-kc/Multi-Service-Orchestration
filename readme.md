### Docker Compose & Reliability lab

#### Container setup
In order to set up the containers, just ensure that you are withing the lab3 folder and then run

    docker compose up -d


#### Verifying working

You can verify that the setup works by runing the grpcurl command 

    grpcurl -plaintext localhost:50051 list myitems.ItemService


Useful commands

- docker ps --format 'table {{.Names}}     {{.Status}}     {{.Ports}}'
