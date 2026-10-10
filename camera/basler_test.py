from pypylon import pylon

def process(image):
    print(image.shape)

with pylon.InstantCamera(pylon.FirstFound) as camera:
    camera.StartGrabbingMax(2)
    for i in range(2):
        with camera.RetrieveResult(5000) as grab_result:
            if grab_result.GrabSucceeded():
                image = grab_result.Array
                process(image)
            print(type(image))
            print("GetImageNumber", grab_result.GetImageNumber())


# Basler a2A2840-67g5m (41951953)
# 41951953

# camera = pylon.InstantCamera({pylon.SerialNumberKey: "41951953"}, pylon.FirstFound)
