from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport

# Select your transport with a defined url endpoint
transport = RequestsHTTPTransport(url="http://localhost:5000/graphql")

# Create a GraphQL client using the defined transport
client = Client(transport=transport, fetch_schema_from_transport=True)

start_sim = gql("""
    mutation {
        runSimulation(sessionId: "1234") {
            runId
        }
    }
""")

result = client.execute(start_sim)
run_id = result['runSimulation']['runId']
print(run_id)

get_results = gql("""
    query getSimulationResults($runId: ID!) {
        simulationResults(runId: $runId) {
            finished
            dates
            metrics {
                id
                values
            }
        }
    }
""")
result = client.execute(get_results, variable_values=dict(runId=run_id))
print(result)
