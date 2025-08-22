import json
def to_obj(s):
    try:
        return json.loads(s)
    except Exception as e:
        print(f"{e}")
        return {}   