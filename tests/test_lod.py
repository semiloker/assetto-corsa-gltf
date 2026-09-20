#!/usr/bin/env python3
"""python tests/test_lod.py -- asserts the LOD-twin rule keeps Left Rear."""
from acgltf.convert import lowres_twins

# A real MX-5 ND slice: three LOD twins among nine corner parts.
mx5 = ['COCKPIT_HR', 'COCKPIT_LR', 'GEO_Cockpit_HR', 'GEO_Cockpit_LR',
       'STEER_HR', 'STEER_LR',
       'WHEEL_LR', 'SUSP_LR', 'RIM_LR', 'DISC_LR', 'GEO_DISC_LR']
assert lowres_twins(mx5) == {'COCKPIT_LR', 'GEO_Cockpit_LR', 'STEER_LR'}

# The one that matters: no _HR anywhere means nothing is dropped, however many
# _LR there are. This is every car's rear-left corner.
assert lowres_twins(['WHEEL_LR', 'SUSP_LR', 'SPRING_LR', 'ROLL_BAR_LR']) == set()

# Casing is the modders' business, not the rule's (lotus_exige_s_roadster).
assert lowres_twins(['GEO_Cockpit_HR', 'GEO_cockpit_LR']) == {'GEO_cockpit_LR'}

# An _HR with no partner is the survivor, never a casualty.
assert lowres_twins(['STEER_HR']) == set()

print('ok')
