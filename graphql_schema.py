import uuid

from graphene import (ID, Boolean, Enum, Field, Float, Int, Interface, List,
                      Mutation, ObjectType, Schema, String)

from calc.simulation import simulate_individuals
from variables import get_variable


class ParameterCategory(Enum):
    DISEASE = 1


class Parameter(ObjectType):
    identifier = ID(required=True)
    category = ParameterCategory()


class Intervention(Interface):
    date = String(required=True)


class LimitMobilityIntervention(ObjectType):
    value = Int(required=True)

    class Meta:
        interfaces = (Intervention,)


class VariableResult(ObjectType):
    id = ID(required=True)
    value = Float(required=True)


class DayResults(ObjectType):
    date = String(required=True)
    variables = List(VariableResult, required=True)


class SimulationResults(ObjectType):
    finished = Boolean(required=True)
    days = List(DayResults)


class Query(ObjectType):
    parameters = List(Parameter)
    interventions = List(Intervention)
    simulation_results = Field(SimulationResults, run_id=ID(required=True))

    def resolve_interventions(query, info):
        interventions = get_variable('interventions')
        out = []
        for iv in interventions:
            if iv[0] == 'limit-mobility':
                out.append(LimitMobilityIntervention(date=iv[1], value=iv[2]))
        return out

    def resolve_simulation_results(query, info, run_id):
        return SimulationResults(finished=False)


class InitializeSession(Mutation):
    id = ID(required=True)

    def mutate(root, info):
        return dict(id=uuid.uuid4().hex)


class RunSimulation(Mutation):
    class Arguments:
        session_id = ID(required=True)

    run_id = ID(required=True)

    def mutate(root, info, session_id):
        pass


class RootMutation(ObjectType):
    initialize_session = InitializeSession.Field()
    run_simulation = RunSimulation.Field()


schema = Schema(query=Query, mutation=RootMutation, types=[
    LimitMobilityIntervention
])
