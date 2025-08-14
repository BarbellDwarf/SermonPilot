import inspect

from sermonaudio.node import requests as node_requests

print("Node methods:")
for name, func in inspect.getmembers(node_requests.Node, inspect.isfunction):
    print(name)
