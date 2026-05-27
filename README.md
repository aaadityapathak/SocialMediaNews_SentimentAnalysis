# COMP90024_team_23

## Repository Structure
The main components of this repository are structured in directories as follows:
- `docs`: This includes the submission document and source files.
- `backend`: Here we have the source code for the different components of the backend to be deployed as fission functions. They may also include some scripts to run locally such as backfills.
- `frontend`: Source code for the Streamlit frontend application.
- `specs`: Fission specs for our components.
- `infrastructure`: Terraform infrastructure definitions.
- `database`: Various index definitions.
- `test`: End to end unit tests. Backend components have unit tests in their respective repositories.

## Infrastructure

### Overview
The infrastructure of this project is managed using [Terraform](https://developer.hashicorp.com/terraform) and the [Terraform Openstack Provider](https://registry.terraform.io/providers/terraform-provider-openstack/openstack/latest/docs). This allows consistent management and tracking of our OpenStack infrastructure on Melbourne Research Cloud. The Terraform template is located in the `infrastructure` directory and contains the following main resources:

- The Kubernetes cluster to use, defined in `cluster.tf`

We are using [GitLab itself](https://docs.gitlab.com/user/infrastructure/iac/terraform_state/) to manage terraform states. This avoids the need to keep the state in the repository itself, and handles constructs such as state locking if multiple users are deploying at the same time.

### Setup and Deployment
In order to deploy the infrastructure, you must first set up the required credentials for both OpenStack and GitLab. To do this, copy the `infrastructure/.env.example` file into a `infrastructure/.env` file, and fill in the missing values with your OpenStack username and password, and with your GitLab username and Personal Access Token as the `TF_HTTP_USERNAME` and `TF_HTTP_PASSWORD`. The token must have "api" scope in order to use terraform states. We also use the [Go-task](https://taskfile.dev) utility as a helper to run scripts in what follows, so it would be good to have it installed. The tasks are defined in our `Taskfile.yml`.

Once you have completed the credentials setup above, you can initialise Terraform and install the required providers using `task init`. Under the hood, this just runs `terraform init` with the appropriate backend configurations. Next, you can run `task validate` to validate the template syntax and data types. Finally, to deploy the infrastructure, run `task apply`. This will plan the changes that need to be performed, asks for your approval, and, if given, will proceed to deploy the infrastructure.

## Repository Setup
In order to setup and deploy our services after the initial infrastructure deployment, you must first set up the Python environment with `uv`:
```shell
# create virtual env
uv venv --python 3.13
source .venv/bin/activate

# Install all dependencies
uv sync --all-packages --all-groups --all-extras
```
Next, you need to set up your environment variables and secrets, if they are not aleady on the cluster. These include the credentials for social media data sources and your credentials for the ElasticSearch cluster.

You can find templates for these secrets and env variables in the `backend/k8s-secrets` directory and in the `.env.example` files in `backend/harvesters` and `backend/api`. 

Once these are ready and the secrets are on the cluster, you can deploy the Fission specs, which are all located in `specs` with the Taskfile utility:
```shell
task deploy-fission-specs
```
This will handle packaging all necessary zip files for packages and applying the Fission specifications.

Next, you may also have to deploy the ML inference server. You can do this on this cluster or another cluster of your choice, as long as the processor can access it over the network. To do this, you can deploy it with Helm directly (the chart is in `backend/ml-server/ml-server`). You can check the Values file for possible configurations you can change.

If you want to build the ML Server Docker image, run `task build-image` from the `backend/ml-server` directory. This should handle downloading and preparing the necessary ML models and building the docker image.

Otherwise, you can just pull the image from the public Dockerhub registry at `dstilesr/t23-ml-server`. It is built for Linux and x86_64 architecture. With this you should be up and running with the backend!

## Frontend - Interface
Once you have deployed the backend, you can run the frontend application to visualise the sentiment data. The application is implemented with [`streamlit`](https://streamlit.io/. To run it, you must first start port forwarding to the Fission router:
```shell
kubectl port-forward -n fission svc/router 9090:80
```
Then, you can run the application from the `frontend` directory with 
```shell
uv run streamlit run political-sentiment.py
```
This should open a browser window where you can interact with the application and data display.

## Comment on Tests
Many of the backend tests require live services, so ou may need provider credentials in order to run them. You will also need to port-forward to the following cluster services:
- ElasticSearch
- Valkey
