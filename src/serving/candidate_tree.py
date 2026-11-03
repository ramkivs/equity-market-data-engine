"""Immutable, generation-pinned ordered candidate records."""
from .persistent_index_map import insert, entries, validate_reference_header

LIMIT = 10 ** 20


def empty():
    return {'root': None, 'count': 0}


def validate_header(header):
    validate_reference_header(header)
    if header['count'] >= LIMIT:
        raise ValueError('candidate tree count exceeds ordinal range')


def _key(ordinal):
    if type(ordinal) is not int or not 0 <= ordinal < LIMIT:
        raise ValueError('invalid candidate tree ordinal')
    return '%020d' % ordinal


class CandidateTree:
    def __init__(self, db, header):
        validate_header(header)
        self.db, self.header = db, header

    def __len__(self):
        return self.header['count']

    def append(self, record):
        if not isinstance(record, dict):
            raise ValueError('invalid candidate tree record')
        ordinal = self.header['count']
        # Reserve room for the new value and the resulting header count.
        if ordinal >= LIMIT - 1:
            raise ValueError('candidate tree ordinal limit')
        self.header['root'] = insert(self.db, self.header['root'], _key(ordinal), {'record': record})
        self.header['count'] += 1


def materialize(db, header):
    validate_header(header)
    found = entries(db, header['root'])
    if len(found) != header['count']:
        raise ValueError('candidate tree count mismatch')
    result = []
    for index in range(header['count']):
        value = found.get(_key(index))
        if not isinstance(value, dict) or set(value) != {'record'} or not isinstance(value['record'], dict):
            raise ValueError('candidate tree ordinal or record mismatch')
        result.append(value['record'])
    return result


def from_list(db, candidates):
    if not isinstance(candidates, list):
        raise ValueError('invalid candidate list')
    header = empty()
    tree = CandidateTree(db, header)
    for record in candidates:
        tree.append(record)
    return header
