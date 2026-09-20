"""Convert Assetto Corsa `.kn5` models to glTF 2.0 / GLB.

    from acgltf import kn5, convert

    model = kn5.load('ks_mazda_mx5_nd.kn5')
    convert.convert([{'file': 'ks_mazda_mx5_nd.kn5',
                      'pos': [0, 0, 0], 'rot': [0, 0, 0]}],
                    'out', 'mx5', flip_uv=False, keep_variants=False,
                    surfaces_ini=None)

The command-line entry points are `kn5-to-gltf`, `kn5-studio` and `kn5-survey`.
"""

__version__ = '1.0.0'
__all__ = ['__version__', 'kn5', 'convert', 'studio', 'survey']
