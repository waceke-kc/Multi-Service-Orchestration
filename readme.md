### Docker Observability

First step was to update the requirements.txt files with
    py-grpc-prometheus==0.8.0
    prometheus_client==0.20.0

#### Prometheus Setup

After adding the recommended code from the lab instructions to the REST and gRPC code and rebuilding the containers, use [Prometheus](http://localhost:9090/targets) to check the status of the prometheus endpoints. 

#### Grafana Setup
After confirming that Prometheus is up, login to Grafana at [Grafana](http://localhost:3000). The initial username is <b>admin</b> and the initial password is also <b>admin</b>. 

Once logged into Grafana, set up the datasource to connect to Prometheus as explained in the instructions. 

After that, create the dashboards as need or you can import the json file <b>Items Dashboard.json</b> which is in the root of this directory and get a premade dashboard. 

#### Important commands

To start the container use:
    docker-compose up -d

To stop the container use:
    docker-compose stop

To check the status of the containers use:
    docker ps

