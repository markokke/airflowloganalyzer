import json
from collections import defaultdict
from datetime import datetime

from bson.objectid import ObjectId


class MongoJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for MongoDB specific types"""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, defaultdict):
            return dict(obj)
        return super().default(obj)
