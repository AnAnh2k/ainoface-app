from vieneu import Vieneu
import inspect

print(inspect.signature(Vieneu.infer))

tts = Vieneu()

print(dir(tts))