

from panda3d.core import NodePath, Shader, Vec4, TransparencyAttrib, LVecBase2i
from panda3d.core import PTAVecBase3f, PTAFloat, PTALMatrix4f, PTAInt, SamplerState
from panda3d.core import CSYupRight, TransformState, Mat4, CSZupRight
from panda3d.core import Texture, UnalignedLMatrix4f, Vec3, PTAFloat


from DebugObject import DebugObject
from MountManager import MountManager
from PipelineSettingsManager import PipelineSettingsManager
from SystemAnalyzer import SystemAnalyzer
from Globals import Globals
from RenderPassManager import RenderPassManager
from LightManager import LightManager
from AmbientOcclusionManager import AmbientOcclusionManager
from GlobalIllumination import GlobalIllumination
from AntialiasingManager import AntialiasingManager
from Scattering import Scattering
from TransparencyManager import TransparencyManager

from GUI.PipelineGuiManager import PipelineGuiManager

from RenderPasses.InitialRenderPass import InitialRenderPass
from RenderPasses.DeferredScenePass import DeferredScenePass
from RenderPasses.ViewSpacePass import ViewSpacePass
from RenderPasses.EdgePreservingBlurPass import EdgePreservingBlurPass
from RenderPasses.CombineGIandAOPass import CombineGIandAOPass
from RenderPasses.LightingPass import LightingPass
from RenderPasses.DynamicExposurePass import DynamicExposurePass
from RenderPasses.FinalPostprocessPass import FinalPostprocessPass


class RenderingPipeline(DebugObject):

    def __init__(self, showbase):
        """ Creates a new pipeline """
        DebugObject.__init__(self, "RenderingPipeline")
        self.showbase = showbase
        self.settings = None
        self.mountManager = MountManager()

    def getMountManager(self):
        """ Returns the mount manager. You can use this to set the
        write directory and base path """
        return self.mountManager

    def loadSettings(self, filename):
        """ Loads the pipeline settings from an ini file """
        self.settings = PipelineSettingsManager()
        self.settings.loadFromFile(filename)

        # This has to be here, before anything is printed
        DebugObject.setOutputLevel(self.settings.pipelineOutputLevel)

    def getSettings(self):
        """ Returns the current pipeline settings """
        return self.settings

    def addLight(self, light):
        self.lightManager.addLight(light)

    def setGILightSource(self, lightSource):
        if self.settings.enableGlobalIllumination:
            self.globalIllum.setTargetLight(lightSource)

    def prepareMaterials(self, nodePath):
        pass

    def getDefaultSkybox(self):
        return NodePath("Skybox")

    def getDefaultObjectShader(self, tesselated=False):
        pass

    def getDefaultTransparencyShader(self):
        """ Returns the default shader for transparent objects """
        if not self.settings.useTransparency:
            raise Exception("Transparency is disabled. You cannot fetch the transparency shader.")
        return self.transparencyManager.getDefaultShader()

    def prepareTransparentObject(self, np):
        np.setTag("ShadowPassShader", "Transparent")

    def getDefaultSkybox(self, scale=40000):
        """ Loads the skybox """
        skybox = loader.loadModel("Models/Skybox/Model.egg.bam")
        skybox.setScale(scale)

        skytex = loader.loadTexture("Data/Skybox/sky.jpg")
        skytex.setWrapU(SamplerState.WMRepeat)
        skytex.setWrapV(SamplerState.WMRepeat)
        skytex.setMinfilter(SamplerState.FTLinear)
        skytex.setMagfilter(SamplerState.FTLinear)
        skybox.setShaderInput("skytex", skytex)

        skybox.setShader(Shader.load(Shader.SLGLSL, 
                "Shader/DefaultShaders/Opaque/vertex.glsl", "Shader/Skybox/fragment.glsl"))
        return skybox


    def reloadShaders(self):
        self.renderPassManager.setShaders()

    def getRenderPassManager(self):
        return self.renderPassManager

    def getSize(self):
        return self._size

    def _createTasks(self):
        self.showbase.addTask(self._preRenderUpdate, "RP_BeforeRender", sort=-5000)
        self.showbase.addTask(self._postRenderUpdate, "RP_AfterRender", sort=5000)

    def _createInputHandles(self):
        # We use PTA's for shader inputs, because that's faster than
        # using setShaderInput
        self.cameraPosition = PTAVecBase3f.emptyArray(1)
        self.lastMVP = PTALMatrix4f.emptyArray(1)
        self.currentMVP = PTALMatrix4f.emptyArray(1)
        self.frameIndex = PTAInt.emptyArray(1)
        self.frameDelta = PTAFloat.emptyArray(1)

        self.renderPassManager.registerStaticVariable("lastMVP", self.lastMVP)
        self.renderPassManager.registerStaticVariable("currentMVP", self.currentMVP)
        self.renderPassManager.registerStaticVariable("frameIndex", self.frameIndex)
        self.renderPassManager.registerStaticVariable("cameraPosition", self.cameraPosition)
        self.renderPassManager.registerStaticVariable("mainCam", self.showbase.cam)
        self.renderPassManager.registerStaticVariable("mainRender", self.showbase.render)
        self.renderPassManager.registerStaticVariable("frameDelta", self.frameDelta)

    def _preRenderUpdate(self, task):
        self._updateInputHandles()
        self.lightManager.updateLights()
        self.lightManager.updateShadows()
        self.lightManager.processCallbacks()
        self.guiManager.update()
        self.transparencyManager.update()
        self.antialiasingManager.update()
        self.renderPassManager.preRenderUpdate()

        if self.globalIllum:
            self.globalIllum.update()

        return task.cont

    def _updateInputHandles(self):
        # Compute camera bounds
        cameraBounds = self.showbase.camNode.getLens().makeBounds()
        cameraBounds.xform(self.showbase.camera.getMat(self.showbase.render))
        self.lightManager.setCullBounds(cameraBounds)

        self.lastMVP[0] = self.currentMVP[0]
        self.currentMVP[0] = self._computeMVP()
        self.frameDelta[0] = Globals.clock.getDt()
        self.cameraPosition[0] = self.showbase.cam.getPos(self.showbase.render)

    def _computeMVP(self):
        """ Computes the current mvp. Actually, this is the
        worldViewProjectionMatrix, but for convience it's called mvp. """
        camLens = self.showbase.camLens
        projMat = Mat4.convertMat(
            CSYupRight,
            camLens.getCoordinateSystem()) * camLens.getProjectionMat()
        transformMat = TransformState.makeMat(
            Mat4.convertMat(self.showbase.win.getGsg().getInternalCoordinateSystem(),
                            CSZupRight))
        modelViewMat = transformMat.invertCompose(
            self.showbase.render.getTransform(self.showbase.cam)).getMat()
        return UnalignedLMatrix4f(modelViewMat * projMat)


    def _createGUIManager(self):
        if self.settings.displayOnscreenDebugger:
            self.guiManager = PipelineGuiManager(self)
            self.guiManager.setup()
        else:
            self.guiManager = None

    def _postRenderUpdate(self, task):
        return task.cont

    def _createViewSpacePass(self):
        if self.renderPassManager.anyPassRequires("ViewSpacePass.normals") or \
            self.renderPassManager.anyPassRequires("ViewSpacePass.position"):
            self.viewSpacePass = ViewSpacePass()
            self.renderPassManager.registerPass(self.viewSpacePass)

    def _createEdgePreservingBlurPass(self):
        haveAo = self.renderPassManager.anyPassProduces("AmbientOcclusionPass.computeResult")
        haveGi = self.renderPassManager.anyPassProduces("GlobalIlluminationPass.diffuseResult")

        if haveAo or haveGi:
            self.edgePreservingBlurPass = EdgePreservingBlurPass()
            self.renderPassManager.registerPass(self.edgePreservingBlurPass)

            if haveAo and haveGi:
                self.combineGIandAOPass = CombineGIandAOPass()
                self.renderPassManager.registerPass(self.combineGIandAOPass)


    def _createDefaultTextureInputs(self):
        for color in ["White", "Black"]:
            emptyTex = loader.loadTexture("Data/Textures/" + color + ".png")
            emptyTex.setMinfilter(SamplerState.FTLinear)
            emptyTex.setMagfilter(SamplerState.FTLinear)
            emptyTex.setWrapU(SamplerState.WMClamp)
            emptyTex.setWrapV(SamplerState.WMClamp)
            self.renderPassManager.registerStaticVariable("emptyTexture" + color, emptyTex)

        texNoise = loader.loadTexture("Data/Textures/noise4x4.png")
        texNoise.setMinfilter(SamplerState.FTNearest)
        texNoise.setMagfilter(SamplerState.FTNearest)
        self.renderPassManager.registerStaticVariable("noise4x4", texNoise)

        # Load the cubemap which is used for point light shadow rendering
        cubemapLookup = self.showbase.loader.loadCubeMap(
            "Data/Cubemaps/DirectionLookup/#.png")
        cubemapLookup.setMinfilter(SamplerState.FTNearest)
        cubemapLookup.setMagfilter(SamplerState.FTNearest)
        cubemapLookup.setFormat(Texture.FRgb8)
        self.renderPassManager.registerStaticVariable("directionToFaceLookup", 
            cubemapLookup)

        # Load the default environment cubemap
        cubemapEnv = self.showbase.loader.loadCubeMap(
            self.settings.defaultReflectionCubemap)
        cubemapEnv.setMinfilter(SamplerState.FTLinearMipmapLinear)
        cubemapEnv.setMagfilter(SamplerState.FTLinearMipmapLinear)
        cubemapEnv.setFormat(Texture.FSrgb)
        self.renderPassManager.registerStaticVariable("defaultEnvironmentCubemap", 
            cubemapEnv)
        self.renderPassManager.registerStaticVariable("defaultEnvironmentCubemapMipmaps", 
            cubemapEnv.getExpectedNumMipmapLevels())


        # Load the color LUT
        colorLUT = loader.loadTexture("Data/ColorLUT/" + self.settings.colorLookupTable)
        colorLUT.setWrapU(SamplerState.WMClamp)
        colorLUT.setWrapV(SamplerState.WMClamp)
        colorLUT.setFormat(Texture.F_rgb16)
        colorLUT.setMinfilter(SamplerState.FTLinear)
        colorLUT.setMagfilter(SamplerState.FTLinear)
        self.renderPassManager.registerStaticVariable("colorLUT", colorLUT)


    def _createGenericDefines(self):
        define = lambda name, val: self.renderPassManager.registerDefine(name, val)
        define("WINDOW_WIDTH", self._size.x)
        define("WINDOW_HEIGHT", self._size.y)

    def _createGlobalIllum(self):
        if self.settings.enableGlobalIllumination:
            self.globalIllum = GlobalIllumination(self)
            self.globalIllum.setup()
        else:
            self.globalIllum = None

    def _precomputeScattering(self):
        if self.settings.enableScattering:
            earthScattering = Scattering(self)
            scale = 1000000000
            earthScattering.setSettings({
                "atmosphereOffset": Vec3(0, 0, - (6360.0 + 9.5) * scale),
                "atmosphereScale": Vec3(scale)
            })
            earthScattering.precompute()
            earthScattering.provideInputs()

    def create(self):
        """ Creates the pipeline """

        self.debug("Setting up render pipeline")

        if self.settings is None:
            self.error("You have to call loadSettings first!")
            return

        self.debug("Checking required Panda3D version ..")
        SystemAnalyzer.checkPandaVersionOutOfDate(29,04,2015)

        # Mount everything first
        self.mountManager.mount()

        # Check if there is already another instance running
        if not self.mountManager.getLock():
            self.fatal("Another instance of the rendering pipeline is already running")
            return

        # Store globals, as cython can't handle them
        self.debug("Setting up globals")
        Globals.load(self.showbase)
        Globals.font = loader.loadFont("Data/Font/SourceSansPro-Semibold.otf")
        Globals.font.setPixelsPerUnit(25)

        self._size = LVecBase2i(self.showbase.win.getXSize(), self.showbase.win.getYSize())

        # Check size
        if self._size.x % 2 == 1:
            self.fatal(
                "The window width has to be a multiple of 2 "
                "(Current: ", self._size.x, ")")
            return
        self._createGUIManager()

        # Some basic scene settings
        self.showbase.camLens.setNearFar(0.1, 50000)
        self.showbase.camLens.setFov(90)
        self.showbase.win.setClearColor(Vec4(1.0, 0.0, 1.0, 1.0))
        self.showbase.render.setAttrib(TransparencyAttrib.make(TransparencyAttrib.MNone), 100)

        # Create render pass matcher
        self.renderPassManager = RenderPassManager()


        self._precomputeScattering()

        # Add initial pass
        self.initialRenderPass = InitialRenderPass()
        self.renderPassManager.registerPass(self.initialRenderPass)

        # Add deferred pass
        self.deferredScenePass = DeferredScenePass()
        self.renderPassManager.registerPass(self.deferredScenePass)

        # Add lighting pass
        self.lightingPass = LightingPass()
        self.renderPassManager.registerPass(self.lightingPass)

        # Add dynamic exposure pass
        self.dynamicExposurePass = DynamicExposurePass(self)
        self.renderPassManager.registerPass(self.dynamicExposurePass)

        # Add final pass
        self.finalPostprocessPass = FinalPostprocessPass()
        self.renderPassManager.registerPass(self.finalPostprocessPass)

        # Create managers
        self.occlusionManager = AmbientOcclusionManager(self)
        self.lightManager = LightManager(self)
        self.antialiasingManager = AntialiasingManager(self)
        self.transparencyManager = TransparencyManager(self)

        self._createGlobalIllum()

        # Make variables available
        self._createGenericDefines()
        self._createInputHandles()
        self._createDefaultTextureInputs()
        self._createViewSpacePass()
        self._createEdgePreservingBlurPass()

        # Finally matchup all the render passes and set the shaders
        self.renderPassManager.createPasses()
        self.renderPassManager.writeAutoconfig()
        self.renderPassManager.setShaders()

        # Create the update tasks
        self._createTasks()


        # TODO: Make GI use render passes
        if self.settings.enableGlobalIllumination:
            self.globalIllum.reloadShader()

        # Give the gui a hint when the pipeline is done loading
        if self.settings.displayOnscreenDebugger:
            self.guiManager.onPipelineLoaded()