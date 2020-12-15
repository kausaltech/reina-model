from pprint import pprint

from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport

# Select your transport with a defined url endpoint
transport = RequestsHTTPTransport(url="http://localhost:5000/graphql")

# Create a GraphQL client using the defined transport
client = Client(transport=transport, fetch_schema_from_transport=True)

if False:
    add_intervention = gql("""
        mutation AddIntervention {
            addIntervention(intervention: {
                date: "2020-12-01",
                type: LIMIT_MOBILITY,
                parameters: [{
                    id: "reduction",
                    value: 50,
                }, {
                    id: "min_age",
                    value: 7,
                }, {
                    id: "max_age",
                    value: 12,
                }, {
                    id: "place",
                    choice: "school",
                }],
            }) {
                id
            }
        }
    """)

    result = client.execute(add_intervention)
    print(result)
    exit()


if False:
    delete_intervention = gql("""
        mutation DeleteIntervention($id: ID!) {
            deleteIntervention(interventionId: $id) {
                ok
            }
        }
    """)

    result = client.execute(delete_intervention, variable_values=dict(id='5'))
    print(result)
    exit()


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


if False:
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


if True:
    start_sim = gql("""
        mutation {
            runSimulation(randomSeed: 1234) {
                runId
            }
        }
    """)

    result = client.execute(start_sim)
    run_id = result['runSimulation']['runId']

    get_results = gql("""
        query getSimulationResults($runId: ID!) {
            simulationResults(runId: $runId) {
                finished
                predictedMetrics {
                    dates
                    metrics {
                        type
                        label
                        intValues
                        floatValues
                    }
                }
            }
        }
    """)
    result = client.execute(get_results, variable_values=dict(runId=run_id))
    print(result)
