#!/usr/bin/env python3
"""Where an imported Assetto Corsa car gets its paint from.

    python tools/test_kn5_paint.py

Two things decide it and both used to be dropped on the floor, which is why a
converted MX-5 or Lancer Evo arrived white:

  * `skins/<name>/` overrides same-named kn5 textures, and the kn5's own copies
    are the untouched export-time template;
  * on a Kunos road car the body colour is not in the diffuse at all -- the
    diffuse is a shared grey panel/AO sheet -- it is the flat `metal_detail`
    texture the shader multiplies over it.

Self-checking, no Assetto Corsa install and no network needed: the textures are
built here in memory.
"""
import io
import os
import shutil
import sys
import tempfile

from acgltf import convert as K
from PIL import Image    # noqa: E402


class FakeModel:
    """Just the one attribute detail_tint and apply_skin read."""

    def __init__(self, textures):
        self.textures = textures


def png(size, pixels):
    """A PNG blob. detail_tint opens whatever PIL opens; DDS is not the point."""
    im = Image.new('RGB', size)
    im.putdata(pixels)
    b = io.BytesIO()
    im.save(b, 'PNG')
    return b.getvalue()


def flat(rgb, size=(64, 64)):
    return png(size, [rgb] * (size[0] * size[1]))


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def test_flat_detail_is_the_paint():
    """The seven MX-5 liveries differ ONLY in this texture. Measured values."""
    cases = {
        'soul_red':    (126, 1, 0),
        'jet_black':   (15, 14, 14),
        'arctic_white': (213, 210, 208),
        'blue_reflex': (30, 33, 36),
    }
    model = FakeModel([(n, True, flat(c)) for n, c in cases.items()])
    for name, rgb in cases.items():
        got = K.detail_tint(model, name, {})
        assert got is not None, '%s: flat colour rejected' % name
        for i, ch in enumerate(rgb):
            # Doubled first (AC's detail maps are neutral at mid-grey), then
            # linearised -- that order is the whole arithmetic.
            want = srgb_to_linear(min(2.0 * ch / 255.0, 1.0))
            assert abs(got[i] - want) < 1e-4, \
                '%s ch%d: %.5f != %.5f' % (name, i, got[i], want)

    # The one that matters most: red must come out red, not grey.
    red = K.detail_tint(model, 'soul_red', {})
    assert red[0] > 0.9 and red[1] < 0.01 and red[2] < 0.01, red
    # ...and black must not come out as the white template.
    black = K.detail_tint(model, 'jet_black', {})
    assert max(black) < 0.02, black


def test_patterned_detail_is_refused():
    """Leather grain and brushed metal are NOT a colour the material can wear.

    Guarded with the full-image extrema, not a downsample: box-averaging a
    grain first collapses it to a constant and the part gets tinted by a mean
    that was never on screen.
    """
    grain = png((64, 64), [(90, 90, 90) if (x + y) % 2 else (150, 150, 150)
                           for y in range(64) for x in range(64)])
    model = FakeModel([('leather', True, grain)])
    assert K.detail_tint(model, 'leather', {}) is None

    # A gradient is not flat either, even though no single pair of neighbours
    # differs by much.
    ramp = png((64, 64), [(x * 4, x * 4, x * 4) for _ in range(64)
                          for x in range(64)])
    model = FakeModel([('ramp', True, ramp)])
    assert K.detail_tint(model, 'ramp', {}) is None

    # Compression noise must not disqualify a colour that is meant to be flat.
    nearly = png((64, 64), [(126 + (i % 3), 1, 0) for i in range(64 * 64)])
    model = FakeModel([('nearly', True, nearly)])
    assert K.detail_tint(model, 'nearly', {}) is not None


def test_flat_colour_gives_the_swatch_and_the_factor_separately():
    """One texture, two numbers, and confusing them ruins the picker.

    The FACTOR is doubled (AC detail maps are neutral at mid-grey) and then
    linearised; the SWATCH is the texture's own colour. Ceramic Metallic is
    (148,148,148) on disk, which doubles past white - drawn from the factor
    every mid-grey car in the list would be the same flat white.
    """
    srgb, lin = K.flat_colour(flat((148, 148, 148)))
    assert srgb == [148, 148, 148], srgb
    assert lin == [1.0, 1.0, 1.0], lin

    srgb, lin = K.flat_colour(flat((126, 1, 0)))
    assert srgb == [126, 1, 0], srgb
    assert lin[0] > 0.9 and lin[1] < 0.01, lin

    assert K.flat_colour(None) is None
    assert K.flat_colour(b'zz' * 16) is None          # too small to be an image


def test_paint_slots_put_the_bodywork_first():
    """colours[0] is the car's colour, and this is the only reason it is.

    A badge and a mirror cap are painted materials too. The panel draws one
    swatch per skin and must not draw the door handle's.
    """
    def mat(name, detail, use=1.0):
        return {'name': name, 'textures': {'txDetail': detail} if detail else {},
                'props': {'useDetail': use}}

    mats = [mat('BADGE', 'chrome_detail.dds'),
            mat('CARPAINT', 'metal_detail.dds'),
            mat('GLASS', ''),                        # no paint slot at all
            mat('TRIM', 'metal_detail.dds', use=0.0)]  # slot present, shader off
    tris = {0: 120, 1: 48000, 3: 900}
    got = K.paint_slots(mats, tris)
    assert [g[1] for g in got] == ['CARPAINT', 'BADGE'], got
    assert got[0][2] == 'metal_detail.dds'

    # No triangle counts at all (a survey that skipped geometry) must still
    # return every painted material rather than dropping them.
    assert len(K.paint_slots(mats, {})) == 2

    # THE MEASURED CASE, from ks_mazda_mx5_nd: the rims are BIGGER than the
    # bodywork (33 024 triangles against 23 554) and are a painted material, so
    # size alone puts the wheels first - and the wheel's tint comes out of the
    # kn5, identical for all seven liveries. Every colour in the picker was then
    # the same grey and changing livery looked like it did nothing.
    mx5 = [mat('EXT_Rim', 'rim_detail.dds'),
           mat('EXT_Carpaint', 'metal_detail.dds'),
           mat('INT_OCC_Carpaint', 'metal_detail.dds'),
           mat('EXT_Plastic_Black', 'plastic_detail.dds')]
    got = K.paint_slots(mx5, {0: 33024, 1: 23554, 2: 5398, 3: 9742})
    assert got[0][1] == 'EXT_Carpaint', got
    # The interior copy of the same paint is the same colour on the inside of
    # the same panels; the exterior is the one a picker should show.
    assert got[1][1] == 'INT_OCC_Carpaint', got
    # An unlabelled material still beats one that positively says wheel: half
    # this library does not name its paint at all.
    plain = [mat('EXT_Rim', 'a.dds'), mat('supra_body_xx', 'b.dds'),
             mat('mystery_01', 'c.dds')]
    assert ([g[1] for g in K.paint_slots(plain, {0: 9e9, 1: 10, 2: 20})]
            == ['supra_body_xx', 'mystery_01', 'EXT_Rim'])


def test_print_skins_format():
    """The line format the editor's import panel parses. Change it and say so.

    First line of each skin is its bodywork (paint_slots guarantees the order),
    a skin with no flat colour still gets a row, and everything that is not a
    row starts with '#'.
    """
    report = {'car': 'ks_fake', 'skins': [
        {'name': '00_red', 'colours': [
            {'material': 'CARPAINT', 'texture': 'm.dds', 'rgb': [126, 1, 0],
             'tris': 4800, 'source': 'skin'},
            {'material': 'BADGE', 'texture': 'c.dds', 'rgb': [200, 200, 200],
             'tris': 12, 'source': 'kn5'}]},
        {'name': 'leather_only', 'colours': []}]}

    buf = io.StringIO()
    keep, sys.stdout = sys.stdout, buf
    try:
        code = K.print_skins(report)
    finally:
        sys.stdout = keep
    lines = buf.getvalue().splitlines()

    assert code == 0
    assert lines[0].startswith('#')
    rows = [ln.split(chr(9)) for ln in lines if not ln.startswith('#')]
    assert [r[1] for r in rows] == ['00_red', '00_red', 'leather_only'], rows
    assert rows[0][2] == 'CARPAINT' and rows[0][3] == '7E0100', rows[0]
    assert rows[2][3] == '-', rows[2]        # no swatch, still listed

    # An encrypted car is an error, not an empty list: an empty list would read
    # as "this car has no liveries", which is a different and wrong statement.
    bad = {'car': 'csp', 'error': 'encrypted', 'skins': []}
    keep2, sys.stderr = sys.stderr, io.StringIO()
    buf2 = io.StringIO()
    keep, sys.stdout = sys.stdout, buf2
    try:
        code = K.print_skins(bad)
    finally:
        sys.stdout, sys.stderr = keep, keep2
    assert code == 1


def test_missing_and_stub_textures():
    model = FakeModel([('stub', True, b'\x00' * 32)])
    assert K.detail_tint(model, 'stub', {}) is None      # encrypted / placeholder
    assert K.detail_tint(model, 'absent', {}) is None    # slot names nothing
    assert K.detail_tint(model, '', {}) is None          # material has no detail

    # The cache must remember a refusal too, or every material re-decodes the
    # same 4 MB texture to be told no again.
    cache = {}
    K.detail_tint(model, 'stub', cache)
    assert 'stub' in cache and cache['stub'] is None


def test_skin_overrides_the_container():
    """`skins/<name>/x.dds` wins over the kn5's own x.dds -- that is the fix."""
    tmp = tempfile.mkdtemp()
    try:
        car = os.path.join(tmp, 'ks_fake_car')
        for s in ('01_black', '00_red', '02_white'):
            os.makedirs(os.path.join(car, 'skins', s))
        k5 = os.path.join(car, 'fake.kn5')
        open(k5, 'wb').close()

        red, white = flat((126, 1, 0)), flat((213, 210, 208))
        open(os.path.join(car, 'skins', '00_red', 'metal_detail.dds'),
             'wb').write(red)
        open(os.path.join(car, 'skins', '02_white', 'metal_detail.dds'),
             'wb').write(white)

        # Default is the FIRST skin, which is what AC itself picks.
        d = K.skin_dir(k5, None)
        assert os.path.basename(d) == '00_red', d

        # Named, case-insensitively.
        assert os.path.basename(K.skin_dir(k5, '02_WHITE')) == '02_white'
        # Opting out keeps the container's own textures.
        assert K.skin_dir(k5, 'none') is None
        # A car with no skins folder is not an error, it is a track-like model.
        bare = os.path.join(tmp, 'bare')
        os.makedirs(bare)
        open(os.path.join(bare, 'x.kn5'), 'wb').close()
        assert K.skin_dir(os.path.join(bare, 'x.kn5'), None) is None

        # The swap itself, and that it reaches detail_tint -- the two halves of
        # the bug in one line: template in the kn5, colour in the skin.
        template = flat((174, 174, 174))
        model = FakeModel([('metal_detail.dds', True, template),
                           ('Skin_00.dds', True, template)])
        before = K.detail_tint(model, 'metal_detail.dds', {})
        # Colourless -- and, doubled, past white: the export-time template
        # tints nothing, which is exactly the car that arrived in primer.
        assert before == [1.0, 1.0, 1.0], before
        n = K.apply_skin(model, K.skin_dir(k5, '00_red'))
        # The NAMES, not a count: --materials needs to say which textures a
        # livery actually overrides, because "the body did not change colour"
        # is usually "this livery does not ship the body's detail map".
        assert n == {'metal_detail.dds'}, n
        tint = K.detail_tint(model, 'metal_detail.dds', {})
        assert tint[0] > 0.9 and tint[1] < 0.01, tint
        # Textures the skin does not carry are left alone.
        assert model.textures[1][2] == template
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_apply_skin_is_a_noop_without_one():
    model = FakeModel([('a.dds', True, b'x' * 200)])
    assert K.apply_skin(model, None) == set()
    assert model.textures[0][2] == b'x' * 200


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok  %s' % name)
    print('all good')
