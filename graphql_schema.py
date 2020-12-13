import uuid

from graphene import (ID, Boolean, Enum, Field, Float, Int, Interface, List,
                      Mutation, ObjectType, Schema, String)
from graphql import GraphQLError

from calc.simulation import simulate_individuals
from common import cache
from flask import session
from simulation_thread import SimulationThread
from variables import get_variable


class ParameterCategory(Enum):
    DISEASE = 1


class Parameter(ObjectType):
    identifier = ID(required=True)
    category = ParameterCategory()


class Intervention(Interface):
    date = String(required=True)


class ContactPlace(Enum):
    HOME = 1
    WORK = 2
    SCHOOL = 3
    TRANSPORT = 4
    LEISURE = 5
    OTHER = 6


class LimitMobilityIntervention(ObjectType):
    value = Int(required=True)
    min_age = Int()
    max_age = Int()
    contact_place = Field(ContactPlace)

    class Meta:
        interfaces = (Intervention,)


class ImportInfectionsIntervention(ObjectType):
    amount = Int(required=True)

    class Meta:
        interfaces = (Intervention,)


class TestingStrategy(Enum):
    NO_TESTING = 0
    ONLY_SEVERE_SYMPTOMS = 1
    ALL_WITH_SYMPTOMS = 2
    CONTACT_TRACING = 3


class TestingStrategyIntervention(ObjectType):
    strategy = Field(TestingStrategy, required=True)
    efficiency = Int()

    class Meta:
        interfaces = (Intervention,)


class Metric(ObjectType):
    id = ID(required=True)
    values = List(Float, required=True)


class SimulationResults(ObjectType):
    run_id = ID(required=True)
    finished = Boolean(required=True)
    end_date = String(required=True)
    dates = List(String)
    metrics = List(Metric)


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
            elif iv[0] == 'import-infections':
                out.append(ImportInfectionsIntervention(date=iv[1], amount=iv[2]))
            elif iv[0] == 'import-infections':
                out.append(ImportInfectionsIntervention(date=iv[1], amount=iv[2]))
            elif iv[0] == 'test-all-with-symptoms':
                out.append(TestingStrategyIntervention(
                    date=iv[1],
                    strategy=TestingStrategy.ALL_WITH_SYMPTOMS,
                ))
            elif iv[0] == 'test-only-severe-symptoms':
                out.append(TestingStrategyIntervention(
                    date=iv[1],
                    strategy=TestingStrategy.ONLY_SEVERE_SYMPTOMS,
                    efficiency=iv[2],
                ))
            elif iv[0] == 'test-with-contact-tracing':
                out.append(TestingStrategyIntervention(
                    date=iv[1],
                    strategy=TestingStrategy.CONTACT_TRACING,
                    efficiency=iv[2]
                ))

        return out

    def resolve_simulation_results(query, info, run_id):
        cache_key = '%s-finished' % run_id
        finished = cache.get(cache_key)
        if finished is None:
            raise GraphQLError('No simulation run active')

        results = cache.get('%s-results' % run_id)
        if results is not None:
            dates = results.index.astype(str).values
            metrics = []
            for col in results.columns:
                metrics.append(Metric(id=col, values=results[col].to_numpy(na_value=None)))
        else:
            dates = []
            metrics = []

        return SimulationResults(finished=finished, dates=dates, metrics=metrics)


class InitializeSession(Mutation):
    id = ID(required=True)

    def mutate(root, info):
        return dict(id=uuid.uuid4().hex)


class RunSimulation(Mutation):
    class Arguments:
        session_id = ID(required=True)

    run_id = ID(required=True)

    def mutate(root, info, session_id):
        thread = SimulationThread(variables=session.copy())
        run_id = thread.cache_key
        thread.start()
        return dict(run_id=run_id)


class RootMutation(ObjectType):
    initialize_session = InitializeSession.Field()
    run_simulation = RunSimulation.Field()


schema = Schema(query=Query, mutation=RootMutation, types=[
    LimitMobilityIntervention, TestingStrategyIntervention, ImportInfectionsIntervention
])
