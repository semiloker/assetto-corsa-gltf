"""kn5 reader - the plain container Assetto Corsa ships models in.

Reads the UNENCRYPTED sections only: node tree, geometry, material names. A file
carrying the CSP `__AC_SHADERS_PATCH_KN5ENC_v1__` trailer keeps its textures and
shader parameters encrypted; those are reported as missing, never decrypted.

Layout is community-reverse-engineered. Two things it is easy to get wrong, and
both cost an afternoon:
  * a material's depthMode is an int32, not a byte;
  * a v6 file has one extra header word before the texture count.
"""
import struct

ENC_MARKER = b'__AC_SHADERS_PATCH_KN5ENC_v1__'

DUMMY, MESH, SKINNED = 1, 2, 3


class Reader:
    def __init__(self, buf):
        self.b = buf
        self.o = 0

    def u8(self):
        v = self.b[self.o]; self.o += 1; return v

    def u32(self):
        v = struct.unpack_from('<I', self.b, self.o)[0]; self.o += 4; return v

    def i32(self):
        v = struct.unpack_from('<i', self.b, self.o)[0]; self.o += 4; return v

    def f32(self):
        v = struct.unpack_from('<f', self.b, self.o)[0]; self.o += 4; return v

    def fn(self, n):
        v = struct.unpack_from('<%df' % n, self.b, self.o); self.o += 4 * n
        return list(v)

    def raw(self, n):
        v = self.b[self.o:self.o + n]; self.o += n; return v

    def s(self):
        n = self.u32()
        v = self.b[self.o:self.o + n].decode('utf-8', 'replace'); self.o += n
        return v


class Node:
    __slots__ = ('type', 'name', 'active', 'matrix', 'children',
                 'pos', 'nrm', 'uv', 'tan', 'idx', 'material',
                 'nverts', 'ntris')

    def __init__(self):
        self.type = 0
        self.name = ''
        self.active = True
        self.matrix = None
        self.children = []
        self.pos = self.nrm = self.uv = self.tan = self.idx = None
        self.material = -1
        # Always present, even when the geometry itself was skipped - a survey
        # of a whole car folder wants the counts and nothing else.
        self.nverts = 0
        self.ntris = 0


class Model:
    def __init__(self):
        self.version = 0
        self.textures = []      # (name, active, data) - data is a stub when encrypted
        self.materials = []
        self.root = None
        self.encrypted = False

    def walk(self):
        out = []

        def rec(n, parent):
            out.append((n, parent))
            for c in n.children:
                rec(c, n)
        rec(self.root, None)
        return out


def load(path, geometry=True):
    """Parse a kn5. With `geometry=False` the vertex and index blocks are seeked
    past instead of unpacked, which is the difference between surveying a folder
    of 200 cars in seconds and in an hour."""
    buf = open(path, 'rb').read()
    m = Model()
    m.encrypted = ENC_MARKER in buf[-64:] or ENC_MARKER in buf

    r = Reader(buf)
    if r.raw(6) != b'sc6969':
        raise ValueError('not a kn5')
    m.version = r.u32()
    if m.version > 5:
        r.u32()

    for _ in range(r.u32()):
        active = r.u32()
        name = r.s()
        data = r.raw(r.u32())
        m.textures.append((name, active, data))

    for _ in range(r.u32()):
        name, shader = r.s(), r.s()
        blend = r.u8()
        tested = bool(r.u8())
        r.i32()                 # depthMode - int32, NOT a byte
        props = {}
        for _ in range(r.u32()):
            pn = r.s()
            props[pn] = r.f32()
            r.raw(4 * 9)        # valueB(2) valueC(3) valueD(4), unused
        texs = {}
        for _ in range(r.u32()):
            slot = r.s(); r.u32(); texs[slot] = r.s()
        m.materials.append({'name': name, 'shader': shader,
                            'props': props, 'textures': texs,
                            'alpha_blend': blend != 0, 'alpha_tested': tested})

    def read_node():
        n = Node()
        n.type = r.i32()
        n.name = r.s()
        nchild = r.i32()
        n.active = bool(r.u8())

        if n.type == DUMMY:
            n.matrix = r.fn(16)
        elif n.type in (MESH, SKINNED):
            r.u8(); r.u8(); r.u8()        # castShadows, visible, transparent
            if n.type == SKINNED:
                for _ in range(r.u32()):
                    r.s(); r.fn(16)
            nv = r.u32()
            n.nverts = nv
            stride = 11 + (8 if n.type == SKINNED else 0)
            if geometry:
                pos = [None] * nv; nrm = [None] * nv
                uv = [None] * nv;  tan = [None] * nv
                for i in range(nv):
                    v = r.fn(11)
                    pos[i] = v[0:3]
                    nrm[i] = v[3:6]
                    uv[i] = v[6:8]
                    tan[i] = v[8:11]
                    if n.type == SKINNED:
                        r.fn(4); r.fn(4)
                n.pos, n.nrm, n.uv, n.tan = pos, nrm, uv, tan
            else:
                r.raw(nv * stride * 4)
            ni = r.u32()
            n.ntris = ni // 3
            if geometry:
                n.idx = list(struct.unpack_from('<%dH' % ni, r.b, r.o))
            r.o += ni * 2
            n.material = r.u32()
            r.u32()                       # layer
            r.f32(); r.f32()              # lodIn / lodOut
            # Only a plain MESH carries a bounding sphere and the isRenderable
            # byte. A SKINNED one ends at lodOut and the next node starts
            # immediately - reading that byte anyway desyncs the whole rest of
            # the tree, which is why a third of the library "failed to parse":
            # every car with a skinned gear lever or steering column.
            if n.type == MESH:
                r.fn(3); r.f32()          # bounding sphere
                r.u8()                    # isRenderable
        else:
            raise ValueError('unknown node type %d at offset %d' % (n.type, r.o))

        for _ in range(nchild):
            n.children.append(read_node())
        return n

    m.root = read_node()
    return m
