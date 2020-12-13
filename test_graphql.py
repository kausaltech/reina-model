from pprint import pprint

from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport

# Select your transport with a defined url endpoint
transport = RequestsHTTPTransport(url="http://localhost:5000/graphql")

# Create a GraphQL client using the defined transport
client = Client(transport=transport, fetch_schema_from_transport=True)

if False:
    validation_metrics_query = gql("""
        query {
            validationMetrics {
                dates
                metrics {
                    id
                    values
                }
            }
        }
    """)

    result = client.execute(validation_metrics_query)
    print(result)
    exit()


if False:
    available_interventions_query = gql("""
        query {
            availableInterventions {
                id
                type
                description
                parameters {
                    id
                    description
                    required
                    ... on InterventionChoiceParameter {
                        choices {
                            id
                            label
                        }
                    }
                    ... on InterventionIntParameter {
                        minValue
                        maxValue
                    }
                }
            }
        }
    """)

    result = client.execute(available_interventions_query)
    pprint(result)
    exit()


if True:
    get_interventions_query = gql("""
        query {
            activeInterventions {
                id
                type
                date
                parameters {
                    id
                    ... on InterventionIntParameter {
                        value
                    }
                    ... on InterventionChoiceParameter {
                        choice {
                            id
                            label
                        }
                    }
                }
            }
        }
    """)
    result = client.execute(get_interventions_query)
    print(result)
    exit()


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
