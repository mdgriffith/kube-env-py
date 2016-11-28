from __future__ import print_function

import jsonpath_rw as path
import yaml
import voluptuous
from voluptuous import Required, Optional, Extra
import pprint
import os

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

config_schema = voluptuous.Schema({
    Required('kube-env'): {
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




if __name__ == "__main__":
    with open("example/kube-env.yaml") as KUBEENV:
        kube_env_file = yaml.load(KUBEENV.read())
        config_schema(kube_env_file)
        kube_env = kube_env_file["kube-env"]
        with open("example/base.yaml") as BASE:

            with open("example/target.yaml", "w") as TARGET:

                doc = BASE.read()
                docs = doc.split("---")

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

                                        print("target path: " + target_path)

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
                                            pprint.pprint(new_base)

                                            # pprint.pprint(found.value)
                    new_doc.append(yaml.dump(new_base, default_flow_style=False, indent=4))
                TARGET.write("---\n".join(new_doc))








