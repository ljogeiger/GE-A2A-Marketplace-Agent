import subprocess


def run_adk_web():
    result = subprocess.run(["adk", "web", "--host", "0.0.0.0"], )


run_adk_web()
