from __future__ import print_function


import os
import os.path
import subprocess
import pprint
import jsonpath_rw as path
import yaml
import voluptuous
from voluptuous import Required, Optional, Extra
import click

##############
# Schemas
##############

diff_schema = voluptuous.Any(
                  voluptuous.Schema({ Required('at'): str
                                    , Required('add'): {Extra:Extra}
                                    , Optional('where'): str
                                    })
                , voluptuous.Schema({ Required('at'): str
                                    , Required('extend'): [Extra]
                                    })
                , voluptuous.Schema({ Required('at'): str
                                    , Required('delete'): str
                                    , Optional('where'): str
                                    })
                )

mod_schema = voluptuous.Schema({ Required('file'): str
                               , Required('where'): str
                               , Required('diff'): [ diff_schema ]
                               })


image_schema = voluptuous.Schema({ Required('name'):str
                                 , Required('location'):str
                                 , Optional('dockerfile', default=None):str
                                 })

directories_schema = voluptuous.Schema({ Required('kubernetes-configs'): str
                                       , Required('deployments'): str
                                       })


config_schema = voluptuous.Schema({
    Required('kube-env'): {
        Required('dirs'): directories_schema,
        Required('docker'): { Required('cmd'): str
                            , Required('images'): [ image_schema ]
                            },
        Required('deployments'): [{ Required('name'): str
                                  , Required('kubernetes-context'): str
                                  , Optional('docker-repo', default=None): str
                                  , Optional('modifications', default=None): [ mod_schema ]
                                  }
                                 ]
        
        }
 })




#######################
# CLI Parameters
#######################


class KubeEnv(click.ParamType):

    name = 'kube-env environment'

    def __init__(self, base_dir=None, filename=None):
        if base_dir is None:
            self.base_dir = ""
        else:
            self.base_dir = base_dir

        if filename is None:
            self.filename = "kube-env.yaml"
        else:
            self.filename = filename


    def convert(self, value, param, ctx):
        try:
            with open(os.path.join(self.base_dir, self.filename)) as KUBEENV:
                config = yaml.load(KUBEENV.read())
                config_schema(config)

                found = None
                for deployment in config["kube-env"]["deployments"]:
                    if deployment["name"] == value:
                        found = deployment
                        break

                if found is None:
                    self.fail('There is no {deploy} deployment in {filename}'.format(
                            deploy=value, filename=os.path.join(self.base_dir, self.filename)), param, ctx)

                return found

        except IOError:
            self.fail('There is no {filename}.yaml config in {base}'.format(
                filename=self.filename, base=self.base_dir), param, ctx)



class Image(click.ParamType):

    name = 'kube-env image'

    def __init__(self, base_dir=None, filename=None):
        if base_dir is None:
            self.base_dir = ""
        else:
            self.base_dir = base_dir

        if filename is None:
            self.filename = "kube-env.yaml"
        else:
            self.filename = filename



    def convert(self, value, param, ctx):
        try:
            with open(os.path.join(self.base_dir, self.filename)) as KUBEENV:
                config = yaml.load(KUBEENV.read())
                config_schema(config)

                if value == "all":
                    return {"all":config["kube-env"]["docker"]["images"]}

                found = None
                for image in config["kube-env"]["docker"]["images"]:
                    if image["name"] == value:
                        found = image
                        break

                if found is None:
                    self.fail('There is no {deploy} deployment in {filename}'.format(
                            deploy=value, filename=os.path.join(self.base_dir, self.filename)), param, ctx)

                return found

        except IOError:
            self.fail('There is no {filename}.yaml config in {base}'.format(
                filename=self.filename, base=self.base_dir), param, ctx)



class KubeFile(click.ParamType):

    name = 'kube-env kube-config'

    def __init__(self, base_dir=None, filename=None):
        if base_dir is None:
            self.base_dir = ""
        else:
            self.base_dir = base_dir

        if filename is None:
            self.filename = "kube-env.yaml"
        else:
            self.filename = filename



    def convert(self, value, param, ctx):
        try:
            with open(os.path.join(self.base_dir, self.filename)) as KUBEENV:
                config = yaml.load(KUBEENV.read())
                config_schema(config)

                kube_dir = config["kube-env"]["dirs"]["kubernetes-configs"]
                deploy_dir = config["kube-env"]["dirs"]["deployments"]

                files = []
                for item in os.listdir(kube_dir):
                    source_item = os.path.join(kube_dir, item)

                    if os.path.isfile(source_item):
                        deployments = []
                        for deployment in config["kube-env"]["deployments"]:


                            if "modifications" in deployment:
                                mods = deployment["modifications"]
                            else:
                                mods = None

                            deployments.append({ "name": deployment["name"]
                                               , "path": os.path.join(deploy_dir, deployment["name"], item)
                                               , "modifications": mods
                                               })

                        files.append({"src":source_item, "deployments":deployments})

                if value == "all":
                    return {"all":files}

                found = None
                for file in files:
                    base = os.path.basename(file["src"])
                    if base == value or base.replace(".yaml", "") == value:
                        found = file
                        break

                if found is None:
                    self.fail('There is no {deploy} file in {filename}'.format(
                            deploy=value, filename=kube_dir), param, ctx)

                return found

        except IOError:
            self.fail('There is no {filename}.yaml config in {base}'.format(
                filename=self.filename, base=self.base_dir), param, ctx)




class Version(click.ParamType):

    name = 'kube-env version'

    def convert(self, value, param, ctx):
        if value not in ['major', 'minor', 'patch']:
            self.fail('{value} needs to be major, minor or patch'.format(value=value), param, ctx)
        return value




def get_path(match):
    '''return an iterator based upon MATCH.PATH. Each item is a path component,
start from outer most item.'''
    if match.context is not None:
        for path_element in get_path(match.context):
            yield path_element
        yield str(match.path)

def update_json(json, path, value):
    '''Update JSON dictionnary PATH with VALUE. Return updated JSON'''
    try:
        first = next(path)
        # check if item is an array
        if first.startswith('[') and first.endswith(']'):
            try:
                first = int(first[1:-1])
            except ValueError:
                pass
        json[first] = update_json(json[first], path, value)
        return json
    except StopIteration:
        return value


cwd = os.getcwd()

def replace_cwd(x):
    if isinstance(x, dict):
        for key in x.keys():
            x[key] = replace_cwd(x[key])
        return x
    elif isinstance(x, basestring) and '{cwd}' in x:
        return x.format(cwd=cwd)
    elif hasattr(x, '__iter__'):
        ys = []
        for y in x:
            ys.append(replace_cwd(y))
        return ys
    else:
        return x


def make_modifications(file, filename, modifications):

    docs = file.split("---")
    new_doc = []
    for file in docs:
        base = yaml.load(file)
        new_base = base.copy()
        for mod in modifications:
            if mod["file"] == filename:

                if "where" in mod:
                    where = mod["where"].split("==")
                    desired = where[1].strip()
                    target = where[0].strip()

                    passing = False
                    for found in path.parse(target).find(base):
                        if found.value == desired:
                            passing = True
                    if not passing:
                        continue

                for diff in mod["diff"]:
                    target_path = diff["at"]
                    if "where" in diff:
                        where = diff["where"].split("==")
                        desired = where[1].strip()
                        target = where[0].strip()
                        found_index = None
                        for i, found in enumerate(path.parse(target_path).find(base)):
                            if target in found.value:
                                if found.value[target] == desired:
                                    found_index = i
                        if found_index is None:
                            continue
                        target_path = target_path[:-3] + "[" + str(found_index) + "]"

                    target = path.parse(target_path)
                    for found in target.find(base):
                        if "add" in diff:
                            new_value = found.value
                            new_value.update(replace_cwd(diff["add"]))
                            update_json(new_base, get_path(found), new_value)
                        elif "extend" in diff:
                            new_value = found.value
                            new_value.extend(replace_cwd(diff["extend"]))
                            update_json(new_base, get_path(found), new_value)
                        elif "delete" in diff:
                            new_value = found.value
                            del new_value[diff["delete"]]
        new_doc.append(yaml.dump(new_base, default_flow_style=False, indent=4))
    return "---\n".join(new_doc)



def semVer(tag):
    nums = tag.split(".")

    if len(nums) != 3:
        return False
    try:
        return [int(nums[0]),int(nums[1]),int(nums[2])]
    except ValueError:
        return False

def isLarger(s1, s2):
    if s1[0] > s2[0]:
        return True
    elif s1[1] > s2[1]:
        return True
    elif s1[2] > s2[2]:
        return True
    else:
        return False


def auto_version(image_name, version_type):
    if version_type not in ["major", "minor", "patch"]:
        print("version needs to be either major, minor, or patch")
        return False
    command = 'docker images {image_name} --format "{{{{.Tag}}}}"'.format(image_name=image_name)
    versions = subprocess.check_output(command, shell=True)
    if versions == "":
        return "1.0.0"

    largest = None
    for vers in versions.split("\n"):
        semver = semVer(vers)
        print(semver)
        if semver:
            if largest is None:
                largest = semver
            elif isLarger(semver, largest):
                largest = semver
    if largest is None:
        return "1.0.0"
    else:
        if version_type == "major":
            largest[0] = largest[0] + 1
            largest[1] = 0
            largest[2] = 0
        elif version_type == "minor":
            largest[1] = largest[1] + 1
            largest[2] = 0
        elif version_type == "patch":
            largest[2] = largest[2] + 1
        return str(largest[0]) + "." + str(largest[1]) + "." + str(largest[2]) 


def get_latest_real_version(image_name):
    command = 'docker images {image_name} --format "{{{{.Tag}}}}"'.format(image_name=image_name)
    versions = subprocess.check_output(command, shell=True)
    if versions == "":
        return "1.0.0"

    largest = None
    for vers in versions.split("\n"):
        semver = semVer(vers)
        print(semver)
        if semver:
            if largest is None:
                largest = semver
            elif isLarger(semver, largest):
                largest = semver
    return largest


@click.command()
@click.argument("image", type=Image())
def build(image):
    """
    Build an image listed in the kube/kube-env.yaml file.
    build {image}
    """
    if "all" in image:
        for im in image["all"]:
            full_image_name = im["name"] + ":latest"
            dockerfile = "Dockerfile"
            if "dockerfile" in image:
                dockerfile = im["dockerfile"]
            location = im["location"]
            subprocess.call("docker build -t {full_image_name} -f {dockerfile} {location}".format(
                full_image_name=full_image_name, location=location, dockerfile=full_dockerfile), shell=True)

    else:
        full_image_name = image["name"] + ":latest"
        dockerfile = "Dockerfile"
        if "dockerfile" in image:
            dockerfile = image["dockerfile"]
        location = image["location"]
        subprocess.call("docker build -t {full_image_name} -f {dockerfile} {location}".format(
            full_image_name=full_image_name, location=location, dockerfile=full_dockerfile), shell=True)


@click.command()
@click.argument("image", type=Image())
@click.argument("env", type=KubeEnv())
@click.argument("version_type", type=Version())
def push(image, env, version_type):
    """
    push {image|all} {environment}
    """
    if "docker-repo" not in env:
        print("no repo to push to")
        return False

    if "all" in image:
        for im in image["all"]:
            tag = get_latest_real_version(im["name"])
            local = im["name"] + ":" + tag
            tagged = env["docker-repo"] + "/" + im["name"] + ":" + tag

            subprocess.call("docker tag {local} {tagged}".format(local=local, tagged=tagged))
            subprocess.call("gcloud docker -- push {tagged}".format(image=full_name), shell=True)

    else:
        tag = get_latest_real_version(im["name"])
        local = im["name"] + ":" + tag
        tagged = env["docker-repo"] + "/" + im["name"] + ":" + tag

        subprocess.call("docker tag {local} {tagged}".format(local=local, tagged=tagged))
        subprocess.call("gcloud docker -- push {tagged}".format(image=full_name), shell=True)


@click.command()
@click.argument("image", type=Image())
@click.argument("version_type", type=Version())
def tag(image, version_type):
    """
    """
    if "all" in image:
        for im in image["all"]:
            tag = auto_version(im["name"], version_type)
            local = image["name"]
            tagged = image["name"] + ":" + tag
            subprocess.call("docker tag {local} {tagged}".format(local=local, tagged=tagged))

    else:
        tag = auto_version(image["name"], version_type)
        local = image["name"]
        tagged = image["name"] + ":" + tag
        subprocess.call("docker tag {local} {tagged}".format(local=local, tagged=tagged))




@click.command()
@click.argument("release_env", type=ReleaseEnv())
@click.argument("version_type", type=Version())
def release(release_env, version_type):
    
    # For every image, get verion numbers

@click.command()
@click.argument("env", type=KubeEnv())
@click.argument("kubefile", type=KubeFile())
def generate(env, kubefile):
    """
    Switch to an environment listed in kube/kube-env file.
    generate {environment} {file|all}
    """
    if "all" in kubefile:
        for kubeconfig in kubefile["all"]:
            for deploy in kubeconfig["deployments"]:
                if deploy["name"] == env["name"]:
                    with open(kubeconfig["src"]) as SRC:
                        if not os.path.exists(os.path.dirname(deploy["path"])):
                            os.makedirs(os.path.dirname(deploy["path"]))
                        with open(deploy["path"], "w") as TARGET:
                            if deploy["modifications"] is not None:
                                TARGET.write(make_modifications( SRC.read()
                                                               , os.path.basename(kubeconfig["src"])
                                                               , deploy["modifications"]
                                                               )
                                            )
                            else:
                                TARGET.write(SRC.read())
    else:
        for deploy in kubefile["deployments"]:
            if deploy["name"] == env["name"]:
                with open(kubefile["src"]) as SRC:
                    if not os.path.exists(os.path.dirname(deploy["path"])):
                        os.makedirs(os.path.dirname(deploy["path"]))
                    with open(deploy["path"], "w") as TARGET:
                        if deploy["modifications"] is not None:
                            TARGET.write(make_modifications( SRC.read()
                                                           , os.path.basename(kubefile["src"])
                                                           , deploy["modifications"]
                                                           )
                                        )
                        else:
                            TARGET.write(SRC.read())
    


@click.command()
@click.argument("env", type=KubeEnv())
@click.argument("kubefile", type=KubeFile())
def apply(env, kubefile):
    """
    Switch to an environment listed in kube/kube-env file.
    apply {environment} {file|all}
    """
    if "all" in kubefile:

        for file in kubefile["all"]:
            for deploy in file["deployments"]:
                if deploy["name"] == env["name"]:
                    if not os.path.exists(deploy["path"]):
                        while True:
                            answer = raw_input("{file} does not exist in {env}, generate it? (Y/n)".format(file=os.path.basename, env=env))
                            if answer.strip() == "n":
                                return False
                            elif answer.strip() == "Y":
                                generate(env, kubefile)

        for file in kubefile["all"]:
            for deploy in file["deployments"]:
                if deploy["name"] == env["name"]:
                    if not os.path.exists(deploy["path"]):
                        subprocess.call("kubectl apply -f {path};".format(path=deploy["path"]), shell=True)

    else:

        for deploy in kubefile["deployments"]:
            if deploy["name"] == env["name"]:
                if not os.path.exists(deploy["path"]):
                    while True:
                        answer = raw_input("{file} does not exist in {env}, generate it? (Y/n)".format(file=os.path.basename, env=env))
                        if answer.strip() == "n":
                            return False
                        elif answer.strip() == "Y":
                            generate(env, kubefile)

        for deploy in kubefile["deployments"]:
            if deploy["name"] == env["name"]:
                if not os.path.exists(deploy["path"]):
                    subprocess.call("kubectl apply -f {path};".format(path=deploy["path"]), shell=True)


@click.command()
def logs():
    """
    Switch to an environment listed in kube/kube-env file.
    """
    pass










