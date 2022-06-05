import os
import subprocess
from os import path
import sys
import yaml

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

INSTALL_SCRIPT_PACKAGE = "deploy"
INSTALLATION_MANIFEST_NAME = "manifest.yaml"
ROOT_NODE='root'


package_list = {}


class ChunkMeta:
    def __init__(self, name, path, version, run_list):
        self.name = name
        self.path = path
        self.version = version
        self.run_list = run_list

    def __str__(self):
        return self.name + '(' + self.version + ')'


class ExitCodes:
    ManifestFileError = 112
    ManifestPayloadError = 113
    ChunkError = 114
    ExecuteError = 115


def parse_package_name(package_name: str):
    parts = package_name.split('@', 1)
    return parts[0], parts[1]


def resolve_deps(arg):
    '''
        Dependency resolver

    "arg" is a dependency dictionary in which
    the values are the dependencies of their respective keys.
    '''
    d=dict((k, set(arg[k])) for k in arg)
    r=[]
    while d:
        # values not in keys (items without dep)
        t=set(i for v in d.values() for i in v)-set(d.keys())
        # and keys without value (items without dep)
        t.update(k for k, v in d.items() if not v)
        # can be done right away
        r.append(t)
        # and cleaned up
        d=dict(((k, v-t) for k, v in d.items() if v))
    return r


if __name__ == '__main__':
    root_path = sys.argv[1]
    for file in os.listdir(root_path):
        artifact_path = path.join(root_path, file)
        if path.isdir(artifact_path):
            try:
                version, name = parse_package_name(file)
                package_list[name] = ChunkMeta(name, artifact_path, version, None)
            except Exception:
                print("[Warning] Malformed directory " + artifact_path + " ... ignore")

    if package_list.get(INSTALL_SCRIPT_PACKAGE) is None:
        print("[Error] No chunk " + INSTALL_SCRIPT_PACKAGE)
        exit(ExitCodes.ManifestFileError)

    manifest_file_path = path.join(package_list[INSTALL_SCRIPT_PACKAGE].path, INSTALLATION_MANIFEST_NAME)
    if not path.isfile(manifest_file_path):
        print("[Error] No " + INSTALLATION_MANIFEST_NAME + " in chunk: " + INSTALL_SCRIPT_PACKAGE)
        exit(ExitCodes.ManifestFileError)

    manifest = None
    with open(manifest_file_path, 'r') as file:
        manifest = yaml.load(file, Loader)

    if manifest is None:
        print("[Error] Cannot parse manifest file")
        exit(ExitCodes.ManifestPayloadError)

    dependency_list = {}
    roots = set()

    for chunk in manifest:
        if chunk not in package_list:
            print("[Error] Chunk: " + chunk + " presented in manifest not exits in update package...")
            exit(ExitCodes.ManifestPayloadError)
        if package_list[chunk].version != manifest[chunk].get('version'):
            print("[Error] Chunk: " + chunk + " version in manifest not equals with downloaded... ["
                  + package_list[chunk].version + '/' + str(manifest[chunk].get('version')) + ']')
            exit(ExitCodes.ChunkError)

        run_list = manifest[chunk].get('run')
        if run_list is None:
            print("[Error] Chunk: " + chunk + " has no run field")
            exit(ExitCodes.ManifestFileError)

        if type(run_list) is not list:
            run_list = (run_list, )
        package_list[chunk].run_list = run_list

        depends_on = manifest[chunk].get('depends-on')
        if depends_on is None:
            roots.add(chunk)
        else:
            if type(depends_on) is list:
                dependency_list[chunk] = depends_on
            else:
                dependency_list[chunk] = (depends_on,)

    for root in roots:
        dependency_list[root] = (ROOT_NODE,)

    dependency_graph = resolve_deps(dependency_list)
    run_queue = []

    print("Calculated dependency list:")
    i = 0
    for layer in dependency_graph[1:]:
        package_str = ""
        for package_name in layer:
            install_package = package_list[package_name]
            run_queue.append(install_package)
            package_str += str(install_package) + ' '
        print('Layer [' + str(i) + ']:  ' + package_str)
        i += 1

    print("Installation started: ")
    for task in run_queue:
        print("[] Running task: " + str(task))
        for command in task.run_list:
            print(".. .. Executing: /bin/bash -c '" + command + "' from " + task.path)
            output = subprocess.run(['/bin/bash', '-c', command], cwd=task.path, capture_output=True)
            print("STDOUT:" + output.stdout.decode("utf-8"))
            print("STDERR:" + output.stderr.decode("utf-8"))

            if output.returncode != 0:
                print("[Error] non zero exit code [" + str(output.returncode) + "]")
                exit(ExitCodes.ExecuteError)
        print()
