from setuptools import setup

setup(
    name='commands',
    version='0.1',
    py_modules=['commands'],
    install_requires=[
        'Click',
        'pyyaml',
        'voluptuous',
        'jsonpath_rw'
    ],
    entry_points='''
        [console_scripts]
        build=kubeenv:build
        push=kubeenv:push
        
    ''',
)
