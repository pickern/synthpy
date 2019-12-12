"""
Keyboard GUI
"""

import pygame, pygame.midi
import synthpy
import time
import threading
import cProfile
import logging
import pyaudio
import queue

# constants
BLACK = (0,0,0)
WHITE = (255, 255, 255)
COLORKEY = (255, 255, 0)
SCALE = 2
OCTAVES = 5

WHITEKEYS = [1, 3, 5, 6, 8, 10, 12]
BLACKKEYS = [2, 4, 7, 9, 11]

CHUNK_SIZE = 64
FS = 44100
CHANNELS = 1
FPS=100


"""
Dict for pygame event -> note number
First col corresponds to key sequence, second corresponds to note number

TODO:
Add midi
"""
EVENT2NUMBER = {
122: [1, 1],
120: [2, 3],
99: [3, 5],
118: [4, 6],
98: [5, 8],
110: [6, 10],
109: [7, 12],
115: [8, 2],
100: [9, 4],
103: [10, 7],
104: [11, 9],
106: [12, 11],
113: [13, 13],
119: [14, 15],
101: [15, 17],
114: [16, 18],
116: [17, 20],
121: [18, 22],
117: [19, 24],
50: [20, 14],
51: [21, 16],
53: [22, 19],
54: [23, 21],
55: [24, 23],
105: [25, 25]
}

"""
Image Utility
"""
def image_at(rectangle, sheet, scale=1):
    rect = pygame.Rect(rectangle)
    image = pygame.Surface(rect.size)
    image.blit(sheet, (0, 0), rect)
    image = pygame.transform.scale(image, (rect.width*scale, rect.height*scale))
    return image

"""
Keyboard class
"""
class Keyboard:
    # init
    def __init__(self):
        pygame.mixer.pre_init(frequency=FS, size=-16, channels=1, buffer=CHUNK_SIZE)
        # setup synth
        self.synth = synthpy.PolySynthpy()
        # setup pygame
        pygame.init()
        pygame.midi.init()
        if pygame.midi.get_default_input_id() != -1:
            self.input_id = pygame.midi.get_default_input_id()
            self.input = pygame.midi.Input(self.input_id)

        self.display_width = 316*SCALE + 20
        self.display_height = 89*SCALE + 20

        self.gameDisplay = pygame.display.set_mode((self.display_width, self.display_height))
        pygame.display.set_caption("FMpy Keyboard")
        self.clock = pygame.time.Clock()

        # variables
        self.octave = 3

        # slice up keyboard image
        kbdImg = pygame.image.load('kbdopen.png')
        self.kbdBed = image_at((3, 100, 316, 89), kbdImg, SCALE)
        self.whiteKeyUp = image_at((0, 0, 9, 37), kbdImg, SCALE)
        self.whiteKeyDown = image_at((18, 0, 9, 37), kbdImg, SCALE)
        self.blackKeyUp = image_at((11, 0, 6, 26), kbdImg, SCALE)
        self.blackKeyDown = image_at((29, 0, 6, 26), kbdImg, SCALE)

        # set up key positions
        whiteKeys = [] # aux array, white key positions
        blackKeys = [] # aux array, black key positions
        self.keySequence = [] # the important one

        # self.drawQueue = queue.Queue()

        for i in range(0, 36):
            whiteKeys.append(36 + 8*SCALE*i)

        skips = 0
        for i in range(0, 25):
            if (i % 5) == 0 or (i % 5) == 2:
                skips = skips + 1
            blackKeys.append(47 + 8*SCALE*(i+skips - 1))

        whiteKeyIter = 0
        blackKeyIter = 0

        # we have to draw white keys first before black keys on top
        # so 0-7 are the white keys, 8-12 black, for each octave
        for i in range(0, OCTAVES*12 + 1):
            if (i % 12) < 7:
                keyPosition = whiteKeys[whiteKeyIter]
                keyType = self.whiteKeyUp
                whiteKeyIter = whiteKeyIter + 1
                self.keySequence.append([keyType, keyPosition])

            else:
                keyPosition = blackKeys[blackKeyIter]
                keyType = self.blackKeyUp
                blackKeyIter = blackKeyIter + 1
                self.keySequence.append([keyType, keyPosition])

    # exit
    def exit(self):
        pygame.quit
        if pygame.midi.get_default_input_id() != -1:
            self.input.close()
        pygame.midi.quit()
        quit()

    # display keys
    def kbd(self, x, y):
        # draw everythin (could be optimized)
        self.gameDisplay.blit(self.kbdBed, (x, y))
        for i in range(0, OCTAVES*12 + 1):
            self.gameDisplay.blit(self.keySequence[i][0], (self.keySequence[i][1], 110))

    # event handlers (to interface with synthpy)
    def keyDown(self, keyNumber):
        self.synth.on_press(EVENT2NUMBER[keyNumber][1] + 36)
        if ((EVENT2NUMBER[keyNumber][0] - 1) % 12 ) < 7:
            self.keySequence[EVENT2NUMBER[keyNumber][0] - 1][0] = self.whiteKeyDown
            # drawQueue.push
        else:
            self.keySequence[EVENT2NUMBER[keyNumber][0] - 1][0] = self.blackKeyDown

    def keyUp(self, keyNumber):
        self.synth.on_release(EVENT2NUMBER[keyNumber][1] + 36)
        if ((EVENT2NUMBER[keyNumber][0]  - 1) % 12) < 7:
            self.keySequence[EVENT2NUMBER[keyNumber][0] - 1][0] = self.whiteKeyUp
        else:
            self.keySequence[EVENT2NUMBER[keyNumber][0] - 1][0] = self.blackKeyUp

    def midiKeyDown(self, keyNumber, velocity=128):
        self.synth.on_press(keyNumber, velocity/128.0)

    def midiKeyUp(self, keyNumber):
        self.synth.on_release(keyNumber)

    def audioLoop(self):
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(rate=FS,
                        channels=1,
                        format=pyaudio.paFloat32,
                        output=True,
                        frames_per_buffer=CHUNK_SIZE)

        data = self.synth.pygameCallback()
        while True:
            self.stream.write(data)
            data = self.synth.pygameCallback()

        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()

        # refresh, called every frame
    def refresh(self, frame_count):
        self.clock.tick(FS/CHUNK_SIZE)

        # split up the work
        if frame_count == 0:
            self.gameDisplay.fill(WHITE)

        if frame_count == 1:
            self.kbd(10,10)

        if frame_count == 2:
            pygame.display.update()


def mainLoop(keyboard):
    frame_count = 0
    while True:
        handleInputs(keyboard)
        keyboard.refresh(frame_count)
        frame_count = (frame_count + 1) % 10


def handleInputs(theKeyboard):
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            theKeyboard.exit()

        if event.type == pygame.KEYDOWN and event.key in EVENT2NUMBER:
            theKeyboard.keyDown(event.key)

        if event.type == pygame.KEYUP and event.key in EVENT2NUMBER:
            theKeyboard.keyUp(event.key)


def main():
    theKeyboard = Keyboard()

    # print device info
    for i in range(0, pygame.midi.get_count()):
        print(pygame.midi.get_device_info(i))

    """
    Model of synpthy voices
    """
    oscAdsr = (0, .4, .4, .5)
    oscMix = .5
    oscTune = 8

    fm1Adsr = (0, .15, .6, 1)
    fm1Index = 2
    fm1Harm1 = 2
    fm1Harm2 = 1

    fm2Adsr = (0, .2, .5, .1)
    fm2Index = 2
    fm2Harm1 = 1
    fm2Harm2 = 1

    fm3Adsr = (0, .1, .7, .5)
    fm3Index = 2
    fm3Harm1 = 1
    fm3Harm2 = .5
    # theKeyboard.midiKeyDown(48)
    """
    MAIN LOOP
    """

    # start audio thread
    audioThread = threading.Thread(target=theKeyboard.audioLoop, daemon=True)
    audioThread.start()

    mainLoop(theKeyboard)

    audioThread.close()

if __name__ == "__main__":
    # cProfile.run('main()')
    main()
