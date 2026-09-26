import subprocess
import os
import yaml
from os.path import abspath, join

with open(abspath(join(__file__, "..", "..", "config.yaml"))) as f:
    version = yaml.safe_load(f)["version"]
print("Version will be: " + version)
subprocess.run("docker login", shell=True)


platforms = ["amd64", "aarch64"]

os.chdir("hassio-google-drive-backup")
for platform in platforms:
    subprocess.run("docker build -f Dockerfile-addon -t sabeechen/hassio-google-drive-backup-{0}:{1} --build-arg BUILD_FROM=homeassistant/{0}-base .".format(platform, version), shell=True)

for platform in platforms:
    subprocess.run("docker push sabeechen/hassio-google-drive-backup-{0}:{1}".format(platform, version), shell=True)
