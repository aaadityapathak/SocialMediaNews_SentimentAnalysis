# Harvesters

Version **0.2.0**. Source adapters and reusable importers live in `src`; scripts
are compatibility/CLI adapters and `tests` contains offline regressions plus
explicit live integration checks. See the [ingestion guide](../../docs/ingestion.md)
for all providers, batching controls, failure behavior, and backfill commands.

From the prepared workspace environment, run `python -m pytest` in this
directory. To run every service, use `python scripts/test_all.py` from the
repository root. Live tests require `--run-integration`.


## Connecting to ElasticSearch
In order to connect to our Elasticsearch instance from your PC, you must first retrieve the password, which is stored on a secret in the Kubernetes cluster. To get it, run
```shell
export KUBECONFIG=path/to/the/kube/config
echo $(kubectl get secret -n elastic elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
```
The user you will use to log in to kibana is `elastic` and the password is the value returned by the above script. Next, open a new terminal to forward a port from your local machine to the Kibana instance on the cluster:
```shell
kubectl port-forward -n elastic svc/kibana-kb-http 5601:5601
```
Now you can access Kibana on your browser at `https::localhost:5601` (note the use of HTTPS protocol!). You may skip warnings about certificates for connecting. Once you are logged in to Kibana, go to the Elasticsearch tab, and there you should be able to retrieve an `API Key`. Save it in the appropriate `.env` file, as it will be used by Python clients to access Elasticsearch. Next, port forward on another terminal to allow access to Elasticsearch itself from your PC: 
```shell
kubectl port-forward -n elastic svc/elasticsearch-es-http 9200:9200
 ```
Now you should be able to access Elasticsearch programmatically at `https://localhost:9200` (note the HTTPS again!).

## Mastodon

### Setup
In order to set up data harvesting with Mastodon, you must first create an account on a Mastodon server. Then, you must set up a Mastodon application credentials to pull data from the server where you created your account. To do this, you must first set up the following environment variables in a `.env` file in this directory:
```dotenv
MASTODON_APP_NAME=""
MASTODON_BASE_URL=""
MASTODON_USER_AGENT="unimelb-c90024-t23"
```
The base URL here is the URL of the mastodon server where you set up your account, such as `https://mastodon.social`, for example. Once you have this, go to the `src` folder and run the script to get an Auth token: `uv run --env-file=../.env get_mastodon_token.py`. Follow the instructions and you will get your auth token, which will be printed to the screen. Once you have the token, add it to your `.env` as the variable `MASTODON_AUTH_TOKEN="<your-token>"`.

The Mastodon api reference is [here](https://docs.joinmastodon.org/methods/timelines/).

### Harvesting
Once you have set up the above credentials, you can harvest Mastodon data using the `mastodon_retrieve` package. Run it from the `src` directory with
```shell
uv run --env-file ../.env python -m mastodon_retrieve gather --hashtags "australia;victoria;melbourne"
```
This will gather data for the last month and store it to a JSON Lines file. Run `uv run --env-file ../.env python -m mastodon_retrieve --help` to see more options.

### Streaming
In order to receive posts as they come in (which can yield much higher data volume), you may use the stream method on mastodon. This cannot be run from the CLI, but it will run on Fission. This will stream the records to a Valkey queue for later processing.
If you exclude the `hashtags` parameter, this will run the streaming from the public timeline of the instance. This will only work on smaller instances and not on `mastodon.social`.

## Youtube

Prerequisites:
- Set your YOUTUBE_API_KEY in .env (see **API Keys** in https://developers.google.com/youtube/registering_an_application)

### Collect data and store in ES
1. Run
```sh
# make sure you are in backend/harvesters/src
uv run --env-file ../.env python -m youtube
```

2. If you want to customize the query, you can use the `--query` flag as below. See other examples in `backend/harvesters/src/youtube/defaults.py`
```sh
uv run --env-file ../.env python -m youtube stream --query '{"main topic": ["specific search 1","specific search 2"]}'
```

