import json
from datetime import datetime
from bson.objectid import ObjectId
from collections import defaultdict

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