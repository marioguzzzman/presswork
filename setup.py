#!/usr/bin/env python
# -*- coding: utf-8 -*-
""" The setup script. Started from excellent boilerplate given by audreyr/cookiecutter-pypackage.
"""
import codecs
import os

from setuptools import setup, find_packages

# setup.py quirk - it's OK to subclass `install` (*IS* actually a class), but must alias to avoid name collision
from setuptools.command.install import install as SetuptoolsInstallCommand

HERE = os.path.abspath(os.path.dirname(__file__))

with codecs.open('README.md', encoding='utf-8') as readme_file:
    readme = readme_file.read()

NLTK_VERSION='3.2.4'

_requirements_cli = [
    'Click>=6.0',
]

_requirements_server = [
    'Flask==0.12.2',
    'Flask-WTF==0.14.2',
    'WTForms==2.1',
]

# these could all be split up, but really purpose of 'Presswork' is to bring a couple of things together into an
# instant-gratification sandbox. so, a compromise: just make things clear-cut, even though I'm 'bundling' them.
requirements = _requirements_cli + _requirements_server + [
    'PyYAML',

    # Third party markov chain text generators
    # (No need to include PyMarkovChain here, is forked and inlined into this repository - PyMarkovChainFork)
    "markovify==0.6.0",

    # Want those lovely NLTK tokenizers!
    'nltk==' + NLTK_VERSION,

    # Depend on BeautifulSoup4 mainly for the marvellous UnicodeDammit utility.
    # (would be nice if we could depend on JUST that, but that's not published on its own.)
    'beautifulsoup4==4.6.0',  # bs4.UnicodeDammit
]

setup_requirements = [
    'pytest-runner',

    # NLTK is required during setup.py if we want to have setup.py download the NLTK corpora.
    'nltk==' + NLTK_VERSION,
]

with codecs.open(os.path.join(HERE, 'requirements_dev.txt'), encoding='utf-8') as f:
    test_requirements = [line.strip() for line in f.read().split('\n')]

_required_nltk_corpora = [
    'punkt',
    'treebank',

    # required by MosesDetokenizer - 'misc/perluniprops' aka 'perluniprops'
    'perluniprops'
]

class InstallWithNLTKCorpora(SetuptoolsInstallCommand):
    """ Extend the behavior of `python setup.py install` to also fetch/install NLTK corpora.

    Where does NLTK data install corpora? NLTK has a few fallback options, so few users need to think about it.
    However if you hit an issue or wish to control it, you can:
        - out-of-box way using NLTK: you can set `NLTK_DATA` environment variable (no code change needed)
        - if you need more info, see official NLTK docs, and/or this thread:
          https://stackoverflow.com/questions/3522372 for more info
    """
    def run(self):
        # setuptools is an oldie goldie. super() is not supported by base class (it's an "old style class")
        SetuptoolsInstallCommand.do_egg_install(self)

        import nltk
        for corpus in _required_nltk_corpora:
            nltk.download(corpus)

setup(
    name='presswork',
    version='0.3.1',
    description="A workbench for text generation using Markov Chains. "
                "A little Flask app (only for local use), and a CLI that supports piping. "
                "Pluggable pieces, various extension points. Have fun!",
    long_description=readme,
    author="Michael Floering",
    author_email='michael.floering@gmail.com',
    url='https://github.com/hangtwenty/presswork',
    packages=find_packages(include=['presswork']),
    entry_points={
        'console_scripts': [
            'presswork=presswork.cli:main'
        ]
    },
    include_package_data=True,
    install_requires=requirements,
    license="GNU General Public License v3",
    zip_safe=False,
    keywords='presswork',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.7',
    ],
    test_suite='tests',
    tests_require=test_requirements,
    setup_requires=setup_requirements,

    cmdclass={
        'install': SetuptoolsInstallCommand,
        'install_with_nltk_corpora': InstallWithNLTKCorpora,
    },
)
