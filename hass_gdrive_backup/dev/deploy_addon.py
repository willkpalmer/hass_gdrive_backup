import subprocess
import os
import yaml
from os.path import abspath, join

with open(abspath(join(__file__, "..", "..", "config.yaml"))) as f:
    version = yaml.safe_load(f)["version"]
print("Version will be: " + version)
subprocess.run("docker login", shell=True)


platforms = ["amd64", "aarch64"]

os.chdir("hass_gdrive_backup")
for platform in platforms:
    subprocess.run("docker build -f Dockerfile-addon -t willkpalmer/hass_gdrive_backup-{0}:{1} --build-arg BUILD_FROM=homeassistant/{0}-base .".format(platform, version), shell=True)

for platform in platforms:
    subprocess.run("docker push willkpalmer/hass_gdrive_backup-{0}:{1}".format(platform, version), shell=True)
