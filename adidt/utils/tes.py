import json
import re


def tryint(value):
    try:
        out = int(value, 0)
    except ValueError:
        return value
    return out


class StructTree:
    @staticmethod
    def get_block(data: str, startpattern: str):
        m = re.search(startpattern, data)
        if not m:
            raise ValueError(f'unable to find {startpattern}')

        s = m.start()
        lvl, e = 0, 0
        for i, c in enumerate(data[s:]):
            if c == '{':
                if lvl == 0:
                    sob = i + 1
                lvl += 1

            elif c == '}':
                lvl -= 1
                if lvl == 0:
                    eob = i
                    break

        return data[s + sob:s + eob]

    def __init__(self, name, pattern, type='struct', children: list=[]):
        self.name = name
        self.pattern = pattern
        self.type = type
        self.children = {c.name: c for c in children}
        self._data = {}

    def __getitem__(self, key):
        return self.children[key]

    def __str__(self, level=0):
        print(f'{"    " * level} - {self.name}')
        for c in self.children.values():
            c.print(level=level+1)

    def __repr__(self):
        return json.dumps(self.data)

    @property
    def data(self):
        return { self.name: self._data }

    def parse(self, data: str):
        field_expr = r'^\s*\.(?P<name>\S*)\s*=\s*(?P<value>[^,\s]*),?(?P<comment>.*)$'
        self.block = self.get_block(data, self.pattern)

        if self.type == 'array':
            self._data = [tryint(i) for i in self.block.split(',')]
            return

        keydata = self.block
        for child in self.children.values():
            child.parse(keydata)
            keydata = keydata.replace(child.block, '')

        for m in re.finditer(field_expr, keydata, re.MULTILINE):
            self._data[m.groupdict()['name']] = tryint(m.groupdict()['value'])

        for name, child in self.children.items():
            self._data[name] = child._data


def parse_talise_config_c(file):
    with open(file, 'r') as f:
        data = f.read()

    tree = StructTree(name='talInit', pattern='taliseInit_t talInit =', children=[
        StructTree(name='spiSettings', pattern='.spiSettings ='),
        StructTree(name='rx', pattern='.rx =', children=[
            StructTree(name='rxProfile', pattern='.rxProfile =', children=[
                StructTree(name='rxFir', pattern='.rxFir ='),
                StructTree(name='rxAdcProfile', type='array', pattern='.rxAdcProfile ='),
                StructTree(name='rxNcoShifterCfg', pattern='.rxNcoShifterCfg ='),
            ]),
            StructTree(name='rxGainCtrl', pattern='.rxGainCtrl =')]),

        StructTree(name='tx', pattern='.tx =', children=[
            StructTree(name='txProfile', pattern='.txProfile =', children=[
                StructTree(name='txFir', pattern='.txFir ='),
                StructTree(name='loopBackAdcProfile', pattern='.loopBackAdcProfile =', type='array'),
            ]),
        ]),

        StructTree(name='obsRx', pattern='.obsRx =', children=[
            StructTree(name='orxProfile', pattern='.orxProfile =', children=[
                StructTree(name='rxFir', pattern='.rxFir ='),
                # StructTree(name='orxLowPassAdcProfile', pattern='.orxLowPassAdcProfile =', type='array'),
                # StructTree(name='orxBandPassAdcProfile', pattern='.orxBandPassAdcProfile =', type='array'),
                StructTree(name='orxMergeFilter', pattern='.orxMergeFilter  =', type='array'),
            ]),
            StructTree(name='orxGainCtrl', pattern='.orxGainCtrl ='),
        ]),
        StructTree(name='clocks', pattern='.clocks ='),
        StructTree(name='jesd204Settings', pattern='.jesd204Settings =', children=[
                StructTree(name='framerA', pattern='.framerA ='),
                StructTree(name='framerB', pattern='.framerB ='),
                StructTree(name='deframerA', pattern='.deframerA ='),
                StructTree(name='deframerB', pattern='.deframerB ='),
        ]),
    ])

    tree.parse(data)
    return tree
