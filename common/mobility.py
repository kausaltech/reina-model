from flask_babel import lazy_gettext as _


MOBILITY_PLACES = {
    'retail_and_recreation': dict(name=_('Retail and recreation')),
    'grocery_and_pharmacy': dict(name=_('Grocery and pharmacy')),
    'parks': dict(name=_('Parks')),
    'transit_stations': dict(name=_('Transit stations')),
    'workplaces': dict(name=_('Workplaces')),
    'residential': dict(name=_('Residential')),
}
