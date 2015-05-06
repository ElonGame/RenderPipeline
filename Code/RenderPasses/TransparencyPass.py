
from panda3d.core import Shader

from Code.Globals import Globals
from Code.RenderPass import RenderPass
from Code.RenderTarget import RenderTarget

class TransparencyPass(RenderPass):

    def __init__(self):
        RenderPass.__init__(self)

    def getID(self):
        return "TransparencyPass"

    def getRequiredInputs(self):
        return {
            "sceneTex": "LightingPass.resultTex",
            "cameraPosition": "Variables.cameraPosition",
            "currentMVP": "Variables.currentMVP",
            "positionTex": "DeferredScenePass.wsPosition",
            "mainCam": "Variables.mainCam",
            "mainRender": "Variables.mainRender",
            "fallbackCubemap": "Variables.defaultEnvironmentCubemap",
            "fallbackCubemapMipmaps": "Variables.defaultEnvironmentCubemapMipmaps",
            "depthTex": "DeferredScenePass.depth",

            "pixelCountBuffer": "Variables.transpPixelCountBuffer",
            "spinLockBuffer": "Variables.transpSpinLockBuffer",
            "listHeadBuffer": "Variables.transpListHeadBuffer",
            "materialDataBuffer": "Variables.transpMaterialDataBuffer",

        }

    def setShaders(self):
        shader = Shader.load(Shader.SLGLSL, 
            "Shader/DefaultPostProcess.vertex",
            "Shader/TransparencyPass.fragment")
        self.target.setShader(shader)

    def create(self):
        self.target = RenderTarget("TransparencyPass")
        self.target.addColorTexture()
        self.target.setColorBits(16)
        self.target.prepareOffscreenBuffer()

    def getOutputs(self):
        return {
            "TransparencyPass.resultTex": lambda: self.target.getColorTexture(),
        }

