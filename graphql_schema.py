import uuid

from calc.datasets import get_detected_cases
from common import cache
from common.interventions import (INTERVENTIONS, ChoiceParameter, IntParameter,
                                  iv_tuple_to_obj)
from flask import session
from graphene import (ID, Boolean, Enum, Field, Float, InputObjectType, Int,
                      Interface, List, Mutation, ObjectType, Schema, String)
from graphql import GraphQLError
from simulation_thread import SimulationThread
from variables import get_variable

InterventionType = Enum('InverventionType', [
    (iv.type.upper().replace('-', '_'), iv.type) for iv in INTERVENTIONS
])


class InterventionParameter(Interface):
    id = ID()
    description = String()
    required = Boolean()


class Choice(ObjectType):
    id = ID()
    label = String()


class InterventionChoiceParameter(ObjectType):
    choices = List(Choice, required=True)
    choice = Field(Choice)

    class Meta:
        interfaces = (InterventionParameter,)


class InterventionIntParameter(ObjectType):
    min_value = Int()
    max_value = Int()
    value = Int()
    unit = String()

    class Meta:
        interfaces = (InterventionParameter,)


class Intervention(ObjectType):
    id = ID()
    date = String()
    description = String()
    type = InterventionType()
    parameters = List(InterventionParameter)


class Metric(ObjectType):
    id = ID(required=True)
    values = List(Float, required=True)


class DailyMetrics(ObjectType):
    dates = List(String)
    metrics = List(Metric)


class SimulationResults(ObjectType):
    run_id = ID(required=True)
    finished = Boolean(required=True)
    end_date = String(required=True)
    predicted_metrics = Field(DailyMetrics, required=True)


def iv_to_graphql_obj(iv, obj_id=None):
    params = []
    iv_params = iv.parameters or []
    for p in iv_params:
        if isinstance(p, IntParameter):
            params.append(InterventionIntParameter(
                id=p.id, description=p.label, required=p.required,
                min_value=p.min_value,
                max_value=p.max_value,
                unit=p.unit,
                value=getattr(p, 'value', None),
            ))
        elif isinstance(p, ChoiceParameter):
            choices = [Choice(id=c.id, label=c.label) for c in p.choices]
            c = getattr(p, 'choice', None)
            if c is not None:
                choice = Choice(id=c.id, label=c.label)
            else:
                choice = None
            params.append(InterventionChoiceParameter(
                id=p.id, description=p.label, required=p.required,
                choices=choices, choice=choice,
            ))
        else:
            raise Exception('Unknown parameter type')
    return Intervention(
        id=obj_id, type=iv.type, description=iv.label, date=getattr(iv, 'date', None), parameters=params
    )


class Query(ObjectType):
    available_interventions = List(Intervention)
    active_interventions = List(Intervention)
    simulation_results = Field(SimulationResults, run_id=ID(required=True))
    validation_metrics = Field(DailyMetrics)
    area_name = String(required=True)
    area_name_long = String(required=True)

    def resolve_available_interventions(query, info):
        out = []
        for iv in INTERVENTIONS:
            out.append(iv_to_graphql_obj(iv))

        return out

    def resolve_active_interventions(query, info):
        interventions = get_variable('interventions')
        out = []
        for idx, iv in enumerate(interventions):
            obj = iv_to_graphql_obj(iv_tuple_to_obj(iv), obj_id=idx)
            out.append(obj)
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

        daily_metrics = DailyMetrics(dates=dates, metrics=metrics)
        return SimulationResults(
            run_id=run_id, finished=finished, predicted_metrics=daily_metrics
        )

    def resolve_validation_metrics(query, info):
        df = get_detected_cases()
        dates = df.index.astype(str).values
        metrics = []
        for col in df.columns:
            metrics.append(Metric(id=col, values=df[col].to_numpy()))
        return DailyMetrics(dates=dates, metrics=metrics)


class RunSimulation(Mutation):
    run_id = ID(required=True)

    def mutate(root, info):
        thread = SimulationThread(variables=session.copy())
        run_id = thread.cache_key
        thread.start()
        return dict(run_id=run_id)


class InterventionInput(InputObjectType):
    date = String()
    parameters = List(InterventionParameter)


class AddIntervention(Mutation):
    class Arguments:
        intervention = InterventionInput(required=True)

    def mutate(root, info, intervention):
        return


class RootMutation(ObjectType):
    run_simulation = RunSimulation.Field()
    # add_intervention = AddIntervention.Field()


schema = Schema(query=Query, mutation=RootMutation, types=[
    InterventionChoiceParameter, InterventionIntParameter
])
