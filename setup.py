"""Setup file for steward"""
from setuptools import setup, find_packages

DATA = {
    'name': 'steward',
    'version': '0.1.0',
    'description': 'Watches over your servers',
    'author': 'Steven Arcangeli',
    'author_email': 'steven@highlig.ht',
    'url': 'http://highlig.ht',
    'packages': find_packages(),
    'entry_points': {
        'console_scripts': [
            'steward-server = steward.scripts:start_server',
            'steward = steward.scripts:client_repl',
            'steward-call = steward.scripts:client_call',
            'steward-listen = steward.scripts:client_listen',
        ]
    },
    'install_requires': {
        'setuptools',
        'tornado',
        'pyzmq',
        'PyYAML',
        'croniter',
    },
    'tests_require': {
        'mock',
        'nose',
    },
}

if __name__ == "__main__":
    setup(**DATA)
