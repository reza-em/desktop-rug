"""OpenGL renderer: draws the cloth mesh into an off-screen multisampled FBO
(orthographic, top-down), then reads it back as a premultiplied QImage that the
translucent raster window paints. Keeping the on-screen window a plain raster
window keeps per-pixel transparency + click-through identical on X11 and
Windows (layered windows), which a native GL window cannot guarantee."""
import math
import numpy as np
import shiboken6
from PySide6.QtCore import QSize
from PySide6.QtGui import (QOffscreenSurface, QOpenGLContext, QSurfaceFormat, QImage,
                           QMatrix4x4, QVector2D, QVector3D)
from PySide6.QtOpenGL import (QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat,
                              QOpenGLShaderProgram, QOpenGLShader, QOpenGLBuffer, QOpenGLTexture)

from .cloth import THICK

GL_FLOAT, GL_UNSIGNED_INT, GL_TRIANGLES, GL_LINES = 0x1406, 0x1405, 0x0004, 0x0001
GL_DEPTH_TEST, GL_BLEND, GL_LESS, GL_LEQUAL = 0x0B71, 0x0BE2, 0x0201, 0x0203
GL_ONE, GL_ONE_MINUS_SRC_ALPHA = 1, 0x0303
GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT = 0x4000, 0x0100
GL_TEXTURE0, GL_TEXTURE1 = 0x84C0, 0x84C1
GL_RENDERER, GL_VERSION = 0x1F01, 0x1F02
GL_MULTISAMPLE, GL_LINE_SMOOTH = 0x809D, 0x0B20

VS = """
attribute vec3 a_pos;
attribute vec3 a_nrm;
attribute vec2 a_uv;
uniform mat4 u_mvp;
uniform float u_mode;        // 0 cloth, 1 shadow, 2 fringe
uniform vec2 u_jitter;
uniform vec2 u_lightoff;
uniform float u_thick;
varying vec3 v_n;
varying vec2 v_uv;
varying float v_z;
void main() {
    vec3 p = a_pos;
    if (u_mode > 0.5 && u_mode < 1.5) {
        p.xy += u_lightoff * (p.z + 2.5) + u_jitter * (1.0 + p.z * 0.07);
        p.z = p.z - 1.5 * u_thick - 1.0;
    }
    gl_Position = u_mvp * vec4(p, 1.0);
    v_n = a_nrm;
    v_uv = a_uv;
    v_z = a_pos.z;
}
"""

FS = """
uniform sampler2D u_front;
uniform sampler2D u_back;
uniform float u_mode;
uniform float u_flip;
uniform float u_shadow_a;
uniform vec3 u_light;
varying vec3 v_n;
varying vec2 v_uv;
varying float v_z;
void main() {
    if (u_mode > 0.5 && u_mode < 1.5) { gl_FragColor = vec4(0.0, 0.0, 0.0, u_shadow_a); return; }
    if (u_mode > 1.5) {
        float l = 0.8 + 0.25 * clamp(v_z / 40.0, 0.0, 1.0);
        gl_FragColor = vec4(v_n * l, 1.0); return;
    }
    bool front = gl_FrontFacing;
    if (u_flip > 0.5) front = !front;
    vec3 n = normalize(v_n);
    if (!front) n = -n;
    vec3 base = front ? texture2D(u_front, v_uv).rgb : texture2D(u_back, v_uv).rgb;
    float diff = max(dot(n, u_light), 0.0);
    float lit = 0.30 + 0.80 * diff;
    vec3 h = normalize(u_light + vec3(0.0, 0.0, 1.0));
    float spec = pow(max(dot(n, h), 0.0), 28.0) * 0.06;
    // wool sheen at grazing angles (folds / crease)
    float rim = pow(1.0 - abs(n.z), 3.0) * 0.10;
    gl_FragColor = vec4(base * lit + vec3(spec + rim * 0.6), 1.0);
}
"""


class GLRenderer:
    name = "opengl"

    def __init__(self):
        self.ok = False
        self.error = ""
        self.fbo = None
        self.fbo_size = None
        self.mesh_key = None
        try:
            self._init()
            self.ok = True
        except Exception as ex:  # any failure -> software fallback
            self.error = str(ex)
            self.ok = False

    def _init(self):
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        fmt.setAlphaBufferSize(8)
        fmt.setRenderableType(QSurfaceFormat.OpenGL)
        self.ctx = QOpenGLContext()
        self.ctx.setFormat(fmt)
        if not self.ctx.create():
            raise RuntimeError("QOpenGLContext.create() failed")
        self.surf = QOffscreenSurface()
        self.surf.setFormat(self.ctx.format())
        self.surf.create()
        if not self.ctx.makeCurrent(self.surf):
            raise RuntimeError("makeCurrent failed")
        self.f = self.ctx.functions()
        self.info = "%s | %s" % (self.f.glGetString(GL_RENDERER), self.f.glGetString(GL_VERSION))
        self.prog = QOpenGLShaderProgram()
        if not self.prog.addShaderFromSourceCode(QOpenGLShader.Vertex, VS):
            raise RuntimeError("vertex shader: " + self.prog.log())
        if not self.prog.addShaderFromSourceCode(QOpenGLShader.Fragment, FS):
            raise RuntimeError("fragment shader: " + self.prog.log())
        self.prog.bindAttributeLocation("a_pos", 0)
        self.prog.bindAttributeLocation("a_nrm", 1)
        self.prog.bindAttributeLocation("a_uv", 2)
        if not self.prog.link():
            raise RuntimeError("link: " + self.prog.log())
        self.vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
        self.vbo.create()
        self.vbo.setUsagePattern(QOpenGLBuffer.DynamicDraw)
        self.ibo = QOpenGLBuffer(QOpenGLBuffer.IndexBuffer)
        self.ibo.create()
        self.fvbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
        self.fvbo.create()
        self.fvbo.setUsagePattern(QOpenGLBuffer.DynamicDraw)
        self.fibo = QOpenGLBuffer(QOpenGLBuffer.IndexBuffer)
        self.fibo.create()
        self.tex_front = self.tex_back = None
        self.flip = 1.0   # y-down ortho reverses winding
        self.ctx.doneCurrent()

    # ------------------------------------------------------------------ resources
    def set_textures(self, front: QImage, back: QImage):
        if not self.ok:
            return
        self.ctx.makeCurrent(self.surf)
        for t in (self.tex_front, self.tex_back):
            if t is not None:
                t.destroy()
        self.tex_front = QOpenGLTexture(front.convertToFormat(QImage.Format_RGBA8888))
        self.tex_back = QOpenGLTexture(back.convertToFormat(QImage.Format_RGBA8888))
        for t in (self.tex_front, self.tex_back):
            t.setMinMagFilters(QOpenGLTexture.LinearMipMapLinear, QOpenGLTexture.Linear)
            t.setWrapMode(QOpenGLTexture.ClampToEdge)
            try:
                t.setMaximumAnisotropy(8.0)
            except Exception:
                pass
        self.ctx.doneCurrent()

    def _ensure_mesh(self, cloth):
        key = (cloth.nx, cloth.ny, cloth.fr_P.shape)
        if key == self.mesh_key:
            return
        nx, ny = cloth.nx, cloth.ny
        i = (np.arange(ny - 1)[:, None] * nx + np.arange(nx - 1)[None, :]).ravel()
        tris = np.stack([i, i + 1, i + nx, i + 1, i + nx + 1, i + nx], -1).astype(np.uint32).ravel()
        self.ibo.bind()
        self.ibo.allocate(tris.tobytes(), tris.nbytes)
        self.n_idx = len(tris)
        E, S, K, _ = cloth.fr_P.shape
        base = (np.arange(E * S) * K)[:, None] + np.arange(K - 1)[None, :]
        lines = np.stack([base, base + 1], -1).astype(np.uint32).ravel()
        self.fibo.bind()
        self.fibo.allocate(lines.tobytes(), lines.nbytes)
        self.n_fidx = len(lines)
        self.vbuf = np.zeros((ny * nx, 8), np.float32)
        self.vbuf[:, 6:8] = cloth.uv.reshape(-1, 2)
        self.fbuf = np.zeros((E * S * K, 8), np.float32)
        ivory = np.array([0.93, 0.88, 0.76], np.float32)
        shade = cloth.fr_shade.reshape(-1)
        k = np.linspace(1.0, 0.86, K)
        col = ivory[None, None, :] * shade[:, None, None] * k[None, :, None]
        self.fbuf[:, 3:6] = col.reshape(-1, 3)
        self.vbo.bind()
        self.vbo.allocate(self.vbuf.nbytes)
        self.fvbo.bind()
        self.fvbo.allocate(self.fbuf.nbytes)
        self.mesh_key = key

    def _ensure_fbo(self, w, h):
        if self.fbo is not None and self.fbo_size == (w, h):
            return
        fmt = QOpenGLFramebufferObjectFormat()
        fmt.setAttachment(QOpenGLFramebufferObject.Depth)
        fmt.setSamples(4)
        self.fbo = QOpenGLFramebufferObject(QSize(w, h), fmt)
        if not self.fbo.isValid():
            fmt.setSamples(0)
            self.fbo = QOpenGLFramebufferObject(QSize(w, h), fmt)
            if not self.fbo.isValid():
                raise RuntimeError("FBO creation failed")
        self.fbo_size = (w, h)

    def _attribs(self):
        p = self.prog
        for loc, n, off in ((0, 3, 0), (1, 3, 12), (2, 2, 24)):
            p.enableAttributeArray(loc)
            p.setAttributeBuffer(loc, GL_FLOAT, off, n, 32)

    # ------------------------------------------------------------------ render
    def render(self, cloth, ox, oy, w, h, dpr=1.0, normals=None):
        self.ctx.makeCurrent(self.surf)
        f = self.f
        pw, ph = max(1, int(math.ceil(w * dpr))), max(1, int(math.ceil(h * dpr)))
        self._ensure_fbo(pw, ph)
        self._ensure_mesh(cloth)
        n = cloth.normals() if normals is None else normals
        self.vbuf[:, 0:3] = cloth.P.reshape(-1, 3)
        self.vbuf[:, 3:6] = n.reshape(-1, 3)
        self.fbuf[:, 0:3] = cloth.fr_P.reshape(-1, 3)

        self.fbo.bind()
        f.glViewport(0, 0, pw, ph)
        f.glClearColor(0, 0, 0, 0)
        f.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        f.glEnable(GL_MULTISAMPLE)
        mvp = QMatrix4x4()
        mvp.ortho(0, w, h, 0, -2000, 2000)
        mvp.translate(-ox, -oy, 0)
        p = self.prog
        p.bind()
        p.setUniformValue("u_mvp", mvp)
        p.setUniformValue1f("u_flip", self.flip)
        p.setUniformValue1f("u_thick", THICK)
        L = QVector3D(-0.32, -0.45, 1.0).normalized()
        p.setUniformValue("u_light", L)
        p.setUniformValue("u_lightoff", QVector2D(0.33, 0.48))
        p.setUniformValue1i("u_front", 0)
        p.setUniformValue1i("u_back", 1)
        f.glActiveTexture(GL_TEXTURE0)
        self.tex_front.bind()
        f.glActiveTexture(GL_TEXTURE1)
        self.tex_back.bind()
        f.glActiveTexture(GL_TEXTURE0)

        # cloth
        f.glEnable(GL_DEPTH_TEST)
        f.glDepthFunc(GL_LEQUAL)
        f.glDepthMask(True)
        f.glDisable(GL_BLEND)
        self.vbo.bind()
        self.vbo.write(0, self.vbuf.tobytes(), self.vbuf.nbytes)
        self._attribs()
        self.ibo.bind()
        p.setUniformValue1f("u_mode", 0.0)
        f.glDrawElements(GL_TRIANGLES, self.n_idx, GL_UNSIGNED_INT, shiboken6.VoidPtr(0))
        # fringe
        self.fvbo.bind()
        self.fvbo.write(0, self.fbuf.tobytes(), self.fbuf.nbytes)
        self._attribs()
        self.fibo.bind()
        p.setUniformValue1f("u_mode", 2.0)
        f.glLineWidth(max(1.0, 1.6 * dpr))
        f.glDrawElements(GL_LINES, self.n_fidx, GL_UNSIGNED_INT, shiboken6.VoidPtr(0))
        # soft shadows (jittered, depth-tested against the cloth, no depth write)
        f.glDepthMask(False)
        f.glDepthFunc(GL_LESS)
        f.glEnable(GL_BLEND)
        f.glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
        self.vbo.bind()
        self._attribs()
        self.ibo.bind()
        p.setUniformValue1f("u_mode", 1.0)
        p.setUniformValue1f("u_shadow_a", 0.075)
        for k in range(8):
            a = k * math.pi / 4
            r = 2.6 if k % 2 else 1.3
            p.setUniformValue("u_jitter", QVector2D(math.cos(a) * r, math.sin(a) * r))
            f.glDrawElements(GL_TRIANGLES, self.n_idx, GL_UNSIGNED_INT, shiboken6.VoidPtr(0))
        f.glDepthMask(True)
        f.glDisable(GL_BLEND)
        p.release()
        img = self.fbo.toImage()
        self.fbo.release()
        self.ctx.doneCurrent()
        if img.format() != QImage.Format_ARGB32_Premultiplied:
            img = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        return img
