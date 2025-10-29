from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in community_waba_events/__init__.py
from community_waba_events import __version__ as version

setup(
	name="community_waba_events",
	version=version,
	description="Manage community events on whatsapp",
	author="Manqala Ltd",
	author_email="dev@manqala.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
