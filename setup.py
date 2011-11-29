from setuptools import setup

setup(
    name = "jscrap",
    version = "0.2",
    packages = ['jscrap'],
    package_data = {
        'jscrap': [
            'js/*js',
            'js/phantom/*js',
        ]
    }
)
