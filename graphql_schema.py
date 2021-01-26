from datetime import date, timedelta
import numpy as np
from flask import session
from graphene import (
    ID, Boolean, Enum, Field, Float, InputObjectType, Int, Interface, List,
    Mutation, ObjectType, Schema, String,
)
from graphql import GraphQLError

from calc.datasets import get_detected_cases, get_population_for_area, get_mobility_data
from calc.simulation import get_age_grouped_population
from common import cache
from common.interventions import (
    INTERVENTIONS, ChoiceParameter, IntParameter, get_intervention, get_active_interventions
)
from common.metrics import ALL_METRICS, METRICS, get_metric
from simulation_thread import SimulationProcess
from variables import get_variable, reset_variables, set_variable, get_session_variables

EventType = Enum(
    'EventType', [(iv.type.upper().replace('-', '_'), iv.type) for iv in INTERVENTIONS]
)

MetricType = Enum('MetricType', [(m.id.upper().replace('-', '_'), m.id) for m in ALL_METRICS])


class EventParameter(Interface):
    id = ID()
    description = String()
    required = Boolean()


class Choice(ObjectType):
    id = ID()
    label = String()


class EventChoiceParameter(ObjectType):
    choices = List(Choice, required=True)
    choice = Field(Choice)

    class Meta:
        interfaces = (EventParameter, )


class EventIntParameter(ObjectType):
    min_value = Int()
    max_value = Int()
    value = Int()
    unit = String()

    class Meta:
        interfaces = (EventParameter, )


class Event(ObjectType):
    id = ID()
    date = String()
    description = String()
    type = EventType()
    parameters = List(EventParameter)
    modified_by_user = Boolean()


class CategorizedIntValues(ObjectType):
    categories = List(String)
    values = List(List(Int))


class Metric(ObjectType):
    type = MetricType(required=True)
    label = String(required=True)
    description = String()
    unit = String()
    color = String()
    is_integer = Boolean(required=True)
    is_simulated = Boolean(required=True)
    is_categorized = Boolean(required=True)
    int_values = List(Int)
    float_values = List(Float)
    categorized_int_values = Field(CategorizedIntValues)


class DailyMetrics(ObjectType):
    dates = List(String)
    metrics = List(Metric, only=List(MetricType))


class Scenario(ObjectType):
    id = ID(required=True)
    label = String(required=True)
    description = String()
    active = Boolean(required=True)


class SimulationResults(ObjectType):
    run_id = ID(required=True)
    finished = Boolean(required=True)
    end_date = String(required=True)
    predicted_metrics = Field(DailyMetrics, required=True)


class PopulationAgeGroup(ObjectType):
    label = String(required=True)
    count = Int(required=True)


class SimulationArea(ObjectType):
    name = String(required=True)
    name_long = String(required=True)
    total_population = Int(required=True)
    age_groups = List(PopulationAgeGroup)


def iv_to_graphql_obj(iv, obj_id=None):
    params = []
    iv_params = iv.parameters
    for p in iv_params:
        if isinstance(p, IntParameter):
            params.append(
                EventIntParameter(
                    id=p.id,
                    description=p.label,
                    required=p.required,
                    min_value=p.min_value,
                    max_value=p.max_value,
                    unit=p.unit,
                    value=iv.values.get(p.id),
                )
            )
        elif isinstance(p, ChoiceParameter):
            choices = [Choice(id=c.id, label=c.label) for c in p.choices]
            c = iv.values.get(p.id)
            if c is not None:
                choice = Choice(id=c.id, label=c.label)
            else:
                choice = None
            params.append(
                EventChoiceParameter(
                    id=p.id,
                    description=p.label,
                    required=p.required,
                    choices=choices,
                    choice=choice,
                )
            )
        else:
            raise Exception('Unknown parameter type')
    return Event(
        id=obj_id,
        type=iv.type,
        description=iv.label,
        date=getattr(iv, 'date', None),
        parameters=params
    )


def results_to_metrics(results, only=None):
    df = results['total']
    adf = results['age_groups']

    dates = df.index.astype(str).values

    selected_metrics = []
    if only is None:
        selected_metrics = METRICS
    else:
        for mtype in only:
            metric_id = mtype.value
            selected_metrics.append(METRICS[metric_id])

    metrics = []

    MIN_CASES = 20
    df['ifr'] = df.dead.divide(
        df.all_infected.clip(lower=MIN_CASES).replace(MIN_CASES, np.inf)
    ) * 100
    df['cfr'] = df.dead.divide(
        df.all_detected.clip(lower=MIN_CASES).replace(MIN_CASES, np.inf)
    ) * 100
    df['ifr'] = df['ifr'].rolling(window=7).mean()
    df['cfr'] = df['cfr'].rolling(window=7).mean()
    df['r'] = df['r'].rolling(window=7).mean()
    df['new_infections'] = df['new_infections'].rolling(window=14).mean().round().astype('Int64').replace({np.nan: None})
    df['detected'] = df['detected'].rolling(window=14).mean().round().astype('Int64').replace({np.nan: None})

    for m in selected_metrics:
        int_values = None
        float_values = None
        categorized_int_values = None

        if m.is_categorized:
            if adf is None:
                continue
            s = adf[m.id]
            categorized_int_values = CategorizedIntValues(categories=s.columns, values=s.values)
        else:
            if m.id not in df.columns:
                raise Exception('metric %s not found in dataset' % m.id())
            vals = df[m.id]
            if m.is_integer:
                int_values = vals.astype('Int32').replace({np.nan: None})
            else:
                vals = vals.astype('float')
                float_values = vals.replace({np.nan: None})

        metrics.append(
            Metric(
                type=m.id,
                label=m.label,
                description=m.description,
                unit=m.unit,
                color=m.color,
                is_integer=m.is_integer,
                is_simulated=m.is_simulated,
                is_categorized=m.is_categorized,
                int_values=int_values,
                float_values=float_values,
                categorized_int_values=categorized_int_values,
            )
        )

    return (dates, metrics)


simulation_processes = {}


class Query(ObjectType):
    available_events = List(Event)
    active_events = List(Event)
    simulation_results = Field(SimulationResults, run_id=ID(required=True))
    validation_metrics = Field(DailyMetrics)
    scenarios = List(Scenario)
    mobility_change_metrics = Field(DailyMetrics)
    area = Field(SimulationArea)

    def resolve_available_events(query, info):
        out = []
        for iv in INTERVENTIONS:
            out.append(iv_to_graphql_obj(iv))

        return out

    def resolve_active_events(query, info):
        interventions = get_active_interventions()
        out = []
        for idx, iv in enumerate(interventions):
            obj = iv_to_graphql_obj(iv, obj_id=idx)
            out.append(obj)
        return out

    def resolve_simulation_results(query, info, run_id):
        cache_key = '%s-finished' % run_id
        finished = cache.get(cache_key)
        if finished is None:
            raise GraphQLError('No simulation run active')

        if finished and run_id in simulation_processes:
            print('Process %s finished, joining' % run_id)
            process = simulation_processes[run_id]
            if process.is_alive():
                print('Process is still alive??')
                simulation_processes[run_id].kill()
            simulation_processes[run_id].join()
            del simulation_processes[run_id]

        error = cache.get('%s-error' % run_id)
        if error is not None:
            raise GraphQLError('Simulation error: %s' % error)

        results = cache.get('%s-results' % run_id)
        if results is not None:
            dates, metrics = results_to_metrics(results)
        else:
            dates = []
            metrics = []

        daily_metrics = DailyMetrics(dates=dates, metrics=metrics)
        return SimulationResults(run_id=run_id, finished=finished, predicted_metrics=daily_metrics)

    def resolve_validation_metrics(query, info):
        df = get_detected_cases()
        sim_start = date.fromisoformat(get_variable('start_date'))
        sim_end = sim_start + timedelta(days=get_variable('simulation_days'))
        df = df[df.index < sim_end]
        df['detected'] = df['all_detected'].diff()
        df['detected'] = df['detected'].rolling(window=14).mean().round().astype('Int64').replace({np.nan: None})
        dates = df.index.astype(str).values

        metrics = []

        for col in df.columns:
            m = get_metric(col)
            if not m:
                raise Exception('no metric found for %s' % col)
            int_values = df[col].to_numpy()
            metrics.append(
                Metric(
                    type=m.id,
                    label=m.label,
                    description=m.description,
                    unit=m.unit,
                    color=m.color,
                    is_integer=m.is_integer,
                    is_simulated=False,
                    int_values=int_values
                )
            )
        return DailyMetrics(dates=dates, metrics=metrics)

    def resolve_mobility_change_metrics(self, info):
        df = get_mobility_data().rolling(7).mean().round().dropna(how='all')
        df = df.astype('Int32').replace({np.nan: None})

        metrics = []
        dates = list(df.index.astype(str).values)

        for col in df:
            s = df[col]

            m = get_metric('%s_mobility_change' % col)
            m_obj = Metric(
                type=m.id,
                label=m.label,
                description=m.description,
                unit=m.unit,
                color=m.color,
                is_integer=m.is_integer,
                is_simulated=False,
                int_values=s.values,
            )
            metrics.append(m_obj)

        return DailyMetrics(dates=dates, metrics=metrics)

    def resolve_area(query, info):
        name = get_variable('area_name')
        name_long = get_variable('area_name_long')
        s = get_age_grouped_population()
        total = s.sum()
        age_groups = [dict(label=x, count=y) for x, y in zip(s.index, s)]
        return dict(
            name=name,
            name_long=name_long,
            total_population=total,
            age_groups=age_groups,
        )

    def resolve_scenarios(query, info):
        scenarios = get_variable('scenarios')
        active_scenario = get_variable('active_scenario')
        out = []
        customized_variables = list(get_session_variables().keys())
        if 'active_scenario' in customized_variables:
            customized_variables.remove('active_scenario')
        if len(customized_variables):
            customized = True
        else:
            customized = False
        for s in scenarios:
            if s['id'] == active_scenario and not customized:
                active = True
            else:
                active = False
            out.append(Scenario(
                id=s['id'], label=s['label'], description=s['description'], active=active
            ))
        return out


class RunSimulation(Mutation):
    class Arguments:
        random_seed = Int()

    run_id = ID(required=True)

    def mutate(root, info, random_seed=None):
        variables = session.copy()
        if random_seed is not None:
            variables['random_seed'] = random_seed

        for key, process in list(simulation_processes.items()):
            if process.exitcode is not None:
                process.join()
                del simulation_processes[key]

        if len(simulation_processes) >= 16:
            raise GraphQLError('System busy')

        process = SimulationProcess(variables=variables)
        run_id = process.cache_key
        process.start()
        if process.pid:
            print('Started process with PID %s (key %s)' % (process.pid, process.cache_key))
            simulation_processes[process.cache_key] = process

        return dict(run_id=run_id)


class EventInputParameter(InputObjectType):
    id = ID(required=True)
    value = Int()
    choice = String()


class EventInput(InputObjectType):
    date = String(required=True)
    type = EventType(required=True)
    parameters = List(EventInputParameter)


class AddEvent(Mutation):
    class Arguments:
        event = EventInput(required=True)

    id = ID(required=True)

    def mutate(root, info, event):
        iv_type = event.type.value

        iv_list = list(get_variable('interventions'))
        obj = get_intervention(iv_type).copy()
        obj.date = event.date
        for p in event.parameters:
            obj.set_param(p.id, p.choice or p.value)
        iv_list.append(obj.make_iv_tuple())
        set_variable('interventions', iv_list)

        return dict(id=len(iv_list) - 1)


class DeleteEvent(Mutation):
    class Arguments:
        event_id = ID(required=True)

    ok = Boolean()

    def mutate(root, info, event_id):
        iv_id = int(event_id)
        iv_list = list(get_variable('interventions'))
        if iv_id >= len(iv_list):
            raise GraphQLError('invalid intervention ID')
        del iv_list[iv_id]
        set_variable('interventions', iv_list)
        return dict(ok=True)


class ResetVariables(Mutation):
    ok = Boolean()

    def mutate(root, info):
        reset_variables()
        return dict(ok=True)


class ActivateScenario(Mutation):
    class Arguments:
        scenario_id = ID(required=True)

    ok = Boolean()

    def mutate(root, info, scenario_id):
        scenarios = get_variable('scenarios')
        if scenario_id:
            for s in scenarios:
                if scenario_id == s['id']:
                    break
            else:
                raise GraphQLError('invalid scenario ID')
        else:
            scenario_id = ''

        reset_variables()
        set_variable('active_scenario', scenario_id)
        return dict(ok=True)


class RootMutation(ObjectType):
    run_simulation = RunSimulation.Field()
    add_event = AddEvent.Field()
    delete_event = DeleteEvent.Field()
    reset_variables = ResetVariables.Field()
    activate_scenario = ActivateScenario.Field()


schema = Schema(query=Query, mutation=RootMutation, types=[EventChoiceParameter, EventIntParameter])
