# Maps skill_name -> (module_path, func_name). robot_agent's SkillRegistry loads this.
# Every skill is a plain function in configs/ra_skills.py that calls the mock robot (configs/backend.py).
# Check against the manifest:
#     python -m robot_agent.contract.check_manifest homeloop_robot/homeloop_robot --strict

_PKG = 'homeloop_robot.configs.ra_skills'

SKILL_CONFIGS: dict = {
    'move': (f'{_PKG}', 'move'),
    'find': (f'{_PKG}', 'find'),
    'pick': (f'{_PKG}', 'pick'),
    'place': (f'{_PKG}', 'place'),
    'put_in': (f'{_PKG}', 'put_in'),
    'open': (f'{_PKG}', 'open'),
    'close': (f'{_PKG}', 'close'),
    'handover': (f'{_PKG}', 'handover'),
    'wait_for_unload': (f'{_PKG}', 'wait_for_unload'),
    'say': (f'{_PKG}', 'say'),
    'announce': (f'{_PKG}', 'announce'),
    'ask': (f'{_PKG}', 'ask'),
    'look': (f'{_PKG}', 'look'),
    'vlm_check': (f'{_PKG}', 'vlm_check'),
    'wait': (f'{_PKG}', 'wait'),
    'dock': (f'{_PKG}', 'dock'),
    'grasp_check': (f'{_PKG}', 'grasp_check'),
    'pose': (f'{_PKG}', 'pose'),
}
