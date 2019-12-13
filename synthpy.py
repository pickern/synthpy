#python 3.6.1
"""
Synthpy - with FM!

TODO:

Fix adsr
    - 0's mess it up

See if hdWaveTables make smooth pitch bend work
    - If not look into interpolation

Fix clicks when changing note
    - not noticable with complex sounds
    - super fast pitchbend?

Why do note sound slightly different on different activations?
    - Might be inconsistent phasing ie phase of base oscillators getting reset on note change

Fix click that happens when you retrigger the envelope before it's done releasing (use lastlevel)
    - also not noticable with complex sounds
    - Rewrite adsr

Key matrix bugs?
    - doesn't happen with midi so must be a keyboard hardware thing
    - playing notes either a half step or an octave apart make it stop accepting keyboard events

Add generic builder for waves/synths, for copying, etc

"""
import numpy as np

import pyaudio

import wave
import sys
import struct

import soundutil as su
import threading

import time
import ctypes

import cProfile

CHUNK_SIZE = 64
FS = 44100
CHANNELS = 1
TICK = 55
TWOPIOVERFS = 2.0*np.pi/FS


# ZEROS = np.zeros(CHUNK_SIZE)


"""
Utility Functions
"""
def note2freq(note, octave):
    return su.NOTE2FREQ[note]*(2**octave)

def number2freq(number, octave):
    while number > 12:
        octave = octave + 1
        number = number - 12
    return su.NUMBER2FREQ[number]*(2**octave)

def freqpluscents(freq, cents):
    # freq - initial note
    # cents - amount of cents (+ or -) to modify freq
    return freq*np.power(2, cents/1200.0)

"""
Synth parts
"""
class PyOsc:
    def __init__(self):
        # get tables sounds from util
        self.sinTable = su.hdSinTable()
        self.triTable = su.hdTriTable()
        self.sawTable = su.hdSawTable()
        self.sqrTable = su.hdSqrTable()
        self.noiseTable = su.hdNoiseTable()

        # maybe use this for tables, not sure if it will impact performance
        self.waveTables = [self.sinTable, self.triTable, self.sawTable, self.sqrTable, self.noiseTable]
        self.waveToTable = {
            'sine':self.sinTable,
            'triangle':self.triTable,
            'saw':self.sawTable,
            'square':self.sqrTable,
            'noise':self.noiseTable
        }

    """
    Simple waveform closures
    """
    def simpleWave(self, start=0, wave='sine'):
        step = 1
        index = start
        if wave in self.waveToTable:
            table = self.waveToTable[wave]
        else:
            table = self.sinTable
        tempt = np.arange(0,CHUNK_SIZE)
        tablelen = len(table)

        def nextSampleVector(freq):
            nonlocal step
            nonlocal index
            adjustedfreq = int(freq*100)
            t = (tempt*adjustedfreq + index) % tablelen
            index = (t[-1] + adjustedfreq) % tablelen
            samples = table[t]
            return samples

        def reset():
            nonlocal index
            index = 0

        return nextSampleVector, reset

    """
    Envelope generator
    """
    def adsr(self, attack, decay, hlevel, release):
        # attack, decay, release, should be in seconds
        # hlevel in the range [0, 1] (this is the sustain)
        # calculate each part of the envelope
        # total = attack + decay + hold + release

        if attack != 0:
            attackStep = 1.0/(FS*attack)
        else:
            attackStep = 1

        if decay != 0:
            decayStep = (1.0-hlevel)/(FS*decay)
        else:
            attackStep = (1.0-hlevel)

        if release != 0:
            releaseStep = hlevel/(FS*release)
        else:
            releaseStep = hlevel

        attackenv = np.linspace(0, attack, int(FS*attack))/attack
        decayenv = np.ones(int(FS*decay)) - np.linspace(0, decay, int(FS*decay))*(1-hlevel)/decay

        # two arrays we'll be using
        attackdecayenvelope = np.concatenate((attackenv, decayenv))
        releaseenvelope = np.ones(int(release*FS))*hlevel - np.linspace(0, release, int(release*FS))*hlevel/release
        lenad = len(attackdecayenvelope) - 1
        lenrel = len(releaseenvelope) - 1

        lastlevel = 0 # will be used if note is retriggered before release is finished, so that attack will start from the last level the note was at
        index = 0
        # note on/off
        on = False
        tempt = np.arange(lenad+lenrel, dtype=int)

        releasescale = 1 # for when note is released before attack env is done
        attackscale = 1

        zeros = np.zeros(CHUNK_SIZE)
        ones = np.ones(CHUNK_SIZE)*hlevel
        t = np.ones(CHUNK_SIZE, dtype=int)

        def nextVector():
            nonlocal index
            nonlocal lastlevel
            nonlocal t

            if index == lenad:
                return ones

            if on:
                bound = lenad-index
                t[0:bound] = tempt[0:bound][0:CHUNK_SIZE]+index
                index = min(index + CHUNK_SIZE, lenad)
                lastlevel = attackdecayenvelope[index]
                return attackdecayenvelope[t]

            elif lastlevel == 0 or index == lenrel:
                return zeros

            else:
                bound = lenrel-index
                t[0:bound] = tempt[0:bound][0:CHUNK_SIZE]+index
                index = min(index + CHUNK_SIZE, lenrel)
                lastlevel = releaseenvelope[index]
                return releasescale*releaseenvelope[t]

        def noteOn():
            nonlocal on
            nonlocal index
            if not on:
                index = 0
                on = True

        def noteOff():
            nonlocal on
            nonlocal index
            nonlocal releasescale
            releasescale = attackdecayenvelope[index] / hlevel
            index = 0
            on = False

        def reset():
            nonlocal index
            nonlocal on
            on = False
            index = 0

        return nextVector, reset, noteOn, noteOff

    """
    Pynth
    """
    def pynth2(self, osc1, osc2, env, mix=.5, tune=0):
        # osc1 - oscillator 1 - should be a closure with nextSample method
        # osc2 - oscillator 2
        # env - envelope
        # mix - float between 0 (full osc1) and 1 (full osc2)
        # tune - pitch difference of osc2 in cents
        pitchdifference = np.power(2, tune/1200.0)
        freq = 440 # init to A4
        pitchdifferencefreq = freq*pitchdifference
        on = False
        index = 0
        velocity = 1

        zeros = np.zeros(CHUNK_SIZE)

        def nextSampleVector():
            envvalue = env[0]()
            if envvalue[0] == 0:
                return zeros
            return envvalue*velocity*((1-mix)*osc1[0](freq) + mix*osc2[0](pitchdifferencefreq))

        def noteOn(newfreq, vel=1):
            nonlocal freq
            nonlocal pitchdifferencefreq
            nonlocal on
            nonlocal velocity

            if not on:
                #reset oscs and env
                reset()
                env[1]()
            velocity = vel
            freq = newfreq
            pitchdifferencefreq = freq*pitchdifference

            on = True
            env[2]()

        def noteOff():
            nonlocal on
            on = False
            env[3]()
            # switch envelope off

        def reset():
            # set osc start indices back to 0
            osc1[1]()
            osc2[1]()

        def pitchBend(value):
            0

        def afterTouch(value):
            0

        def setParams():
            0

        def getEnv():
            0

        return nextSampleVector, reset, noteOn, noteOff, noteOn, afterTouch, setParams, getEnv

    def fmpynth(self, env, mosc, mindex=10, cm=1, mm=1):
        # osc1 - oscillator 1 - should be a closure with nextSample method
        # osc2 - oscillator 2
        # mix - float between 0 (full osc1) and 1 (full osc2)
        # tune - pitch difference of osc2 in cents
        modindex = mindex
        cmult = cm
        mmult = mm
        freq = 440 # init to A4
        FSperiod = 1.0/freq
        cfreq = cmult*freq
        on = False
        index = 0
        velocity = 1
        bend = 0
        tempt = np.arange(0,CHUNK_SIZE)
        outvec = np.ones(CHUNK_SIZE)

        zeros = np.zeros(CHUNK_SIZE)

        def nextSampleVector():
            nonlocal modindex
            nonlocal index
            # nonlocal outvec
            envvalue = env[0]()
            if envvalue[0] == 0:
                return zeros
            TWOPIOVERFSCFREQ = TWOPIOVERFS*cfreq
            t = tempt + index
            index = (t[-1] + 1)%(FSperiod)
            sampvec = envvalue*np.sin(TWOPIOVERFSCFREQ*t+ modindex*mosc[0](), out=outvec)
            # DEAL WITH THIS AT SOME POINT
            return velocity*sampvec

        def noteOn(newfreq, vel=1):
            nonlocal freq
            nonlocal cfreq
            nonlocal on
            nonlocal velocity
            nonlocal FSperiod
            velocity = vel
            freq = newfreq
            FSperiod = (FS*1.0)/newfreq
            cfreq = cmult*freq
            if not on:
                # get ready for a new note
                reset()
            on = True
            # modulator on
            mosc[2](freq*mmult)
            # envelope on
            env[2]()

        def noteOff():
            nonlocal on
            on = False
            # switch modulator off
            mosc[3]()
            # switch envelope off
            env[3]()

        def reset():
            nonlocal index
            index = 0
            # reset modulator
            mosc[1]()
            # reset envelope
            env[1]()

        def pitchBend(value):
            # sounds like shit
            nonlocal freq
            nonlocal cfreq
            diffCents = 200.0*(value - 8192.0)/16383.0
            tempFreq = freqpluscents(freq, diffCents)
            cfreq = cmult*tempFreq
            # modulator on
            mosc[2](tempFreq*mmult)
            # envelope on
            # nonlocal cfreq
            # # midi pitchbend is 0 to 16,383, 8,192 is no bend

            # cfreq = int(freqpluscents(cmult*freq, diffCents))
            # mosc[4](freqpluscents(mmult*freq, diffCents))

        def afterTouch(value):
            0

        def setParams(newIndex, newcmult, newmmult):
            nonlocal modindex
            nonlocal cmult
            nonlocal mmult
            if newIndex != -1:
                modindex = newIndex
            if newcmult != -1:
                cmult = cm
            if newmmult != -1:
                mmult = mm

        def getMosc():
            return mosc

        def getEnv():
            return env

        return nextSampleVector, reset, noteOn, noteOff, pitchBend, afterTouch, setParams, getMosc, getEnv

"""
Control/interface
"""
class PolySynthpy:
    def __init__(self):
        # setup
        self.octave = 0# TODO - controls for octave
        self.note = 1# modified by on_press - find a better way to carry note information
        self.p = pyaudio.PyAudio()
        self.osc = PyOsc()

        self.VOICES = []
        self.AVAILABLEVOICES = [0, 1, 2, 3, 4]
        self.NOTEDICT = {}
        self.NUMVOICES = 5

        self.initVoices()

        self.buffer = (ctypes.c_float * CHUNK_SIZE)()
        self.pack = struct.Struct('{}f'.format(CHUNK_SIZE)).pack

    def initVoices(self):
        oscAdsr = (.1, .4, .9, .1)
        oscWave1 = 'sin'
        oscWave2 = 'sin'
        oscMix = .5
        oscTune = 8

        fm1Adsr = (.1, .1, .6, .1)
        fm1Index = 2
        fm1Harm1 = 1
        fm1Harm2 = 1

        fm2Adsr = (.1, .2, .5, .1)
        fm2Index = 2
        fm2Harm1 = 1
        fm2Harm2 = 1

        fm3Adsr = (.1, .1, .7, .1)
        fm3Index = 3
        fm3Harm1 = 1
        fm3Harm2 = .5
        for i in range(0, self.NUMVOICES):
            # Populate voices
            baseosc = self.osc.pynth2(self.osc.simpleWave(wave=oscWave1), self.osc.simpleWave(wave=oscWave2), self.osc.adsr(oscAdsr[0], oscAdsr[1], oscAdsr[2], oscAdsr[3]), oscMix, oscTune)
            fm1 = self.osc.fmpynth(self.osc.adsr(fm1Adsr[0], fm1Adsr[1], fm1Adsr[2], fm1Adsr[3]), baseosc, fm1Index, fm1Harm1, fm1Harm2)
            fm2 = self.osc.fmpynth(self.osc.adsr(fm2Adsr[0], fm2Adsr[1], fm2Adsr[2], fm2Adsr[3]), fm1, fm2Index, fm2Harm1, fm2Harm2)
            fm3 = self.osc.fmpynth(self.osc.adsr(fm3Adsr[0], fm3Adsr[1], fm3Adsr[2], fm3Adsr[3]), fm2, fm3Index, fm3Harm1, fm3Harm2)
            self.VOICES.append(fm3)

    def start(self):
        self.stream = self.p.open(rate=FS,
                        channels=1,
                        format=pyaudio.paFloat32,
                        output=True,
                        frames_per_buffer=CHUNK_SIZE,
                        stream_callback=self.callback)

    def exit(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()


    def callback(self, in_data, frame_count, time_info, status):
        # get synth samples if key is pressed
        dataarr = ((self.VOICES[0][0]() + self.VOICES[1][0]() + self.VOICES[2][0]() + self.VOICES[3][0]() + self.VOICES[4][0]())/5.0).astype('float32')
        return (dataarr.tobytes(), pyaudio.paContinue)

    def pygameCallback(self):
        # get synth samples if key is pressed
        dataarr = ((self.VOICES[0][0]() + self.VOICES[1][0]() + self.VOICES[2][0]() + self.VOICES[3][0]() + self.VOICES[4][0]())/5.0).astype('float32', copy=False)
        return dataarr.tobytes()

    # setup listener
    # key has to agree with pygame
    def on_press(self, key, velocity=1):
        note = key
        if note not in list(self.NOTEDICT) and len(self.NOTEDICT) < self.NUMVOICES:
            # assign note to first unused voice, guranteed to have 1 by conditional
            self.NOTEDICT[note] = self.AVAILABLEVOICES.pop(0)
            freq = number2freq(note, self.octave)
            self.VOICES[self.NOTEDICT[note]][2](freq, velocity)


    def on_release(self, key, velocity=1):
        note = key
        if note in self.NOTEDICT:
            # make voice available again
            self.VOICES[self.NOTEDICT[note]][3]()
            self.AVAILABLEVOICES.append(self.NOTEDICT[note])
            del self.NOTEDICT[note]

    def editVoice(self, opNum, newIndex=-1, newCMult=-1, newMMult=-1):
        for voice in self.VOICES:
            for i in range(0, opNum):
                voice = voice[7]()
            voice[6](newIndex, newCMult, newMMult)

    def pitchBend(self, value):
        for voice in self.VOICES:
            voice[4](value)

    def afterTouch(self, note):
        0

class MonoSynthpy:
    def __init__(self):
        # setup
        self.octave = 0# TODO - controls for octave
        self.note = 1# modified by on_press - find a better way to carry note information
        self.p = pyaudio.PyAudio()
        self.osc = PyOsc()
        self.NOTESPRESSED = {}
        self.LASTPRESSED = -1

        self.initVoices()

    def initVoices(self):
        oscAdsr = (0, .2, .4, .1)
        oscWave1 = 'square'
        oscWave2 = 'triangle'
        oscMix = .5
        oscTune = 0

        fm1Adsr = (1.9, .3, .6, .2)
        fm1Index = 2
        fm1Harm1 = 2
        fm1Harm2 = 1

        fm2Adsr = (1.7, 5, .5, .3)
        fm2Index = 2
        fm2Harm1 = 1
        fm2Harm2 = 1

        fm3Adsr = (1.3, .7, .6, .4)
        fm3Index = 2
        fm3Harm1 = 1
        fm3Harm2 = 1

        fm4Adsr = (1.1, .9, .6, .5)
        fm4Index = 2
        fm4Harm1 = 1
        fm4Harm2 = 1

        fm5Adsr = (.9, 1.1, .8, .6)
        fm5Index = 2
        fm5Harm1 = 1
        fm5Harm2 = 1

        fm6Adsr = (.7, 1.3, .8, .7)
        fm6Index = 2
        fm6Harm1 = 1
        fm6Harm2 = 1

        fm7Adsr = (.5, 1.7, .8, .8)
        fm7Index = 2
        fm7Harm1 = 1
        fm7Harm2 = 1

        fm8Adsr = (.3, 1.9, .8, .9)
        fm8Index = 2
        fm8Harm1 = 1
        fm8Harm2 = 1

        fm9Adsr = (.2, 2.3, .8, 1)
        fm9Index = 2
        fm9Harm1 = 1
        fm9Harm2 = .5

        fm10Adsr = (0, 1, .8, 1.1)
        fm10Index = 2
        fm10Harm1 = 1
        fm10Harm2 = .5

        baseosc = self.osc.pynth2(self.osc.simpleWave(wave=oscWave1), self.osc.simpleWave(wave=oscWave2), self.osc.adsr(oscAdsr[0], oscAdsr[1], oscAdsr[2], oscAdsr[3]), oscMix, oscTune)
        fm1 = self.osc.fmpynth(self.osc.adsr(fm1Adsr[0], fm1Adsr[1], fm1Adsr[2], fm1Adsr[3]), baseosc, fm1Index, fm1Harm1, fm1Harm2)
        fm2 = self.osc.fmpynth(self.osc.adsr(fm2Adsr[0], fm2Adsr[1], fm2Adsr[2], fm2Adsr[3]), fm1, fm2Index, fm2Harm1, fm2Harm2)
        fm3 = self.osc.fmpynth(self.osc.adsr(fm3Adsr[0], fm3Adsr[1], fm3Adsr[2], fm3Adsr[3]), fm2, fm3Index, fm3Harm1, fm3Harm2)
        fm4 = self.osc.fmpynth(self.osc.adsr(fm4Adsr[0], fm4Adsr[1], fm4Adsr[2], fm4Adsr[3]), fm3, fm4Index, fm4Harm1, fm4Harm2)
        fm5 = self.osc.fmpynth(self.osc.adsr(fm5Adsr[0], fm5Adsr[1], fm5Adsr[2], fm5Adsr[3]), fm4, fm5Index, fm5Harm1, fm5Harm2)
        fm6 = self.osc.fmpynth(self.osc.adsr(fm6Adsr[0], fm6Adsr[1], fm6Adsr[2], fm6Adsr[3]), fm5, fm6Index, fm6Harm1, fm6Harm2)
        fm7 = self.osc.fmpynth(self.osc.adsr(fm7Adsr[0], fm7Adsr[1], fm7Adsr[2], fm7Adsr[3]), fm6, fm7Index, fm7Harm1, fm7Harm2)
        fm8 = self.osc.fmpynth(self.osc.adsr(fm8Adsr[0], fm8Adsr[1], fm8Adsr[2], fm8Adsr[3]), fm7, fm8Index, fm8Harm1, fm8Harm2)
        fm9 = self.osc.fmpynth(self.osc.adsr(fm9Adsr[0], fm9Adsr[1], fm9Adsr[2], fm9Adsr[3]), fm8, fm9Index, fm9Harm1, fm9Harm2)
        fm10 = self.osc.fmpynth(self.osc.adsr(fm10Adsr[0], fm10Adsr[1], fm10Adsr[2], fm10Adsr[3]), fm9, fm10Index, fm10Harm1, fm10Harm2)

        self.VOICE = fm10

    def start(self):
        self.stream = self.p.open(rate=FS,
                        channels=1,
                        format=pyaudio.paFloat32,
                        output=True,
                        frames_per_buffer=CHUNK_SIZE,
                        stream_callback=self.callback)

    def exit(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()

    def callback(self, in_data, frame_count, time_info, status):
        dataarr = []
        # get synth samples if key is pressed
        dataarr = self.VOICE[0]()
        # dataarr = ZEROS
        data = struct.pack('{}f'.format(CHUNK_SIZE), *dataarr)
        if status==4:
            print("underflow")
        return (data, pyaudio.paContinue)

    def pygameCallback(self):
        # get synth samples if key is pressed
        dataarr = self.VOICE[0]().astype('float32', copy=False)
        return dataarr.tobytes()

    # setup listener
    # key has to agree with pygame
    def on_press(self, key, velocity=1):
        note = key
        freq = int(number2freq(note, self.octave))
        # add note to pressed dictionary
        self.NOTESPRESSED[note] = freq
        self.LASTPRESSED = note
        # noteOn
        self.VOICE[2](freq, velocity)

    def on_release(self, key, velocity=1):
        note = key
        # check which key released
        if len(self.NOTESPRESSED) != 0:
            del self.NOTESPRESSED[note]

            if len(self.NOTESPRESSED) == 0:
                self.VOICE[3]()
            elif note == self.LASTPRESSED:
                self.LASTPRESSED = list(self.NOTESPRESSED)[0]
                self.VOICE[2](self.NOTESPRESSED[self.LASTPRESSED])


    def editVoice(self, opNum, newIndex=-1, newCMult=-1, newMMult=-1):
        for voice in self.VOICES:
            for i in range(0, opNum):
                voice = voice[7]()
            voice[6](newIndex, newCMult, newMMult)

    def pitchBend(self, value):
        for voice in self.VOICES:
            voice[4](value)

    def afterTouch(self, note):
        0

    def reset(self):
        for note in list(self.NOTESPRESSED):
            del self.NOTESPRESSED[note]

        self.VOICE[3]()

def test():
    synth = PolySynthpy()
    synth.on_press(48)
    synth.on_press(48+2)
    synth.on_press(48+4)
    synth.on_press(48+6)
    synth.on_press(48+8)
    for i in range(0,1000):
        data = synth.pygameCallback()

if __name__=="__main__":
    cProfile.run('test()')
    # test()
