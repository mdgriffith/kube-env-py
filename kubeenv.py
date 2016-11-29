from __future__ import print_function

import jsonpath_rw as path
import yaml
import voluptuous
from voluptuous import Required, Optional, Extra
import pprint
import os
import os.path
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

                files = []
                for item in os.listdir(kube_dir):
                    pathed_item = os.path.join(kube_dir, item)
                    if os.path.isfile(pathed_item):
                        files.append(pathed_item)

                if value == "all":
                    return {"all":files}

                found = None
                for file in files:
                    if file == value or file.replace(".yaml", "") == value:
                        found = file
                        break

                if found is None:
                    self.fail('There is no {deploy} file in {filename}'.format(
                            deploy=value, filename=kube_dir), param, ctx)

                return found

        except IOError:
            self.fail('There is no {filename}.yaml config in {base}'.format(
                filename=self.filename, base=self.base_dir), param, ctx)







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
        print("replacing!")
        return x.format(cwd=cwd)
    elif hasattr(x, '__iter__'):
        ys = []
        for y in x:
            ys.append(replace_cwd(y))
        return ys
    else:
        return x




def apply_modifications(kube_env, file):

    docs = file.split("---")
    new_doc = []
    for file in docs:
        base = yaml.load(file)
        new_base = base.copy()

        for deployment in kube_env["deployments"]:
            if "modifications" in deployment:
                print("modifications detected")
                for mod in deployment["modifications"]:
                    if mod["file"] == "base.yaml":

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
                                pprint.pprint(diff["where"])
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




def get_kubeenv(name):
    pass

def get_kubefiles(name):
    pass






@click.command()
@click.argument("image", type=Image())
def build(image):
    """
    Build an image listed in the kube/kube-env.yaml file.
    build {image}
    """
    print("Found image!")
    pprint.pprint(image)


@click.command()
@click.argument("image", type=Image())
@click.argument("env", type=KubeEnv())
def push(image, env):
    """
    push {image|all} {environment}
    """
    print("pushing")
    pprint.pprint(image)
    pprint.pprint(env)

@click.command()
@click.argument("env", type=KubeEnv())
@click.argument("kubefile", type=KubeFile())
def generate(env, kubefile):
    """
    Switch to an environment listed in kube/kube-env file.
    generate {environment} {file|all}
    """
    print("generating")
    pprint.pprint(env)
    pprint.pprint(kubefile)


@click.command()
@click.argument("env", type=KubeEnv())
@click.argument("kubefile", type=KubeFile())
def apply():
    """
    Switch to an environment listed in kube/kube-env file.
    apply {environment} {file|all}
    """
    pass

@click.command()
def logs():
    """
    Switch to an environment listed in kube/kube-env file.
    """
    pass



if __name__ == "__main__":
    with open("example/kube-env.yaml") as KUBEENV:
        kube_env_file = yaml.load(KUBEENV.read())
        config_schema(kube_env_file)
        kube_env = kube_env_file["kube-env"]
        with open("example/base.yaml") as BASE:
            with open("example/target.yaml", "w") as TARGET:
                TARGET.write(apply_modifications(kube_env, BASE.read()))









