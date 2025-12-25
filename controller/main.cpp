#include <fstream>
#include <iostream>
#include <SDL.h>
#include <fcntl.h>
#include <unistd.h>
#include <string>
#include <cmath>
#include <thread>
#include <chrono>

#define UPPER_THRESHOLD 32000
#define LOWER_THRESHOLD 200

void sendPipeButton(std::string buttun, std::string pressOrRelease, int pipeID) {
    std::string message = buttun + "\n" + pressOrRelease + "\n\n";
    write(pipeID, message.c_str(), message.size());
}

void sendPipeAnalog(std::string stick, std::string axis, float value, int pipeID) {
    std::string message = stick + "\n" + axis + "\n" + std::to_string(value) + "\n";
    write(pipeID, message.c_str(), message.size());
}

// Deadzone to prevent drift from slight stick movements
const int JOYSTICK_DEAD_ZONE = 8000;



int main() {

    bool quit = false;

    SDL_Event e;

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER | SDL_INIT_SENSOR) < 0) {
        std::cerr << "SDL could not initialize! SDL Error: " << SDL_GetError() << std::endl;
        return -1;
    }

    SDL_GameController* controller = nullptr;

    // 2. Check for attached controllers
    // In a real game, you would handle SDL_CONTROLLERDEVICEADDED events dynamically
    if (SDL_NumJoysticks() < 1) {
        std::cout << "Warning: No joysticks connected!" << std::endl;
    } else {
        // Open the first available controller
        for (int i = 0; i < SDL_NumJoysticks(); ++i) {
            if (SDL_IsGameController(i)) {
                controller = SDL_GameControllerOpen(i);
                if (controller) {
                    std::cout << "Controller connected: " << SDL_GameControllerName(controller) << std::endl;

                    // Optional: Enable Gyroscope and Accelerometer for DualSense
                    SDL_GameControllerSetSensorEnabled(controller, SDL_SENSOR_GYRO, SDL_TRUE);
                    SDL_GameControllerSetSensorEnabled(controller, SDL_SENSOR_ACCEL, SDL_TRUE);

                    // Optional: Set LED Color to Purple (R:255, G:0, B:255)
                    SDL_GameControllerSetLED(controller, 255, 0, 255);
                    break;
                } else {
                    std::cerr << "Could not open game controller " << i << ": " << SDL_GetError() << std::endl;
                }
            }
        }
    }



    SDL_Window* window = SDL_CreateWindow(
     "CLI Listener",
     0, 0, 1, 1,
     SDL_WINDOW_MINIMIZED
 );
    SDL_RaiseWindow(window);

    if (!window) {
        std::cerr << "SDL_CreateWindow Error: " << SDL_GetError() << "\n";
        return 1;
    }

    SDL_SetWindowInputFocus(window);



    // OPEN PIPE
    const char* pipe_path = "/tmp/my_pipe";

    std::cout << "1" << std::endl;

    int fd = open(pipe_path, O_WRONLY);  // open ONCE
    if (fd == -1) return 1;

    std::string message;

    std::cout << "Listening for keyboard events (press 'q' to quit)..." << std::endl;

    while( !quit ) {
        while (SDL_PollEvent( &e ) != 0) {


            // if (e.type == SDL_KEYDOWN) {
            switch (e.type) {
                case SDL_KEYDOWN:
                    switch (e.key.keysym.sym) {
                    case SDLK_ESCAPE:
                            printf("ESCAPE\n");
                            break;
                    case SDLK_a:
                            message = "LEFT";
                            sendPipeButton(message,"press", fd);
                            std::cout << "message written: "<< "LEFT" << std::endl;
                            break;
                    case SDLK_d:
                            message = "RIGHT";
                            sendPipeButton(message, "press",fd);
                            std::cout << "message written: "<< "RIGHT" << std::endl;
                            break;
                    case SDLK_w:
                            message = "UP";
                            sendPipeButton(message,"press", fd);
                            std::cout << "message written: "<< "UP" << std::endl;
                            break;
                    case SDLK_s:
                            message = "DOWN";
                            sendPipeButton(message,"press", fd);
                            std::cout << "message written: "<< "DOWN" << std::endl;
                            break;
                    case SDLK_q:
                            quit = true;
                            printf("Quitting\n");
                            break;
                    }

                    // sendPipeButton(message, fd);

                    // --- Handle Button Presses ---
                case SDL_CONTROLLERBUTTONDOWN:
                    // Only process our specific controller
                    if (e.cbutton.which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controller))) {
                        std::cout << "Button Down: "
                                  << SDL_GameControllerGetStringForButton((SDL_GameControllerButton)e.cbutton.button)
                                  << std::endl;

                        switch (e.cbutton.button) {
                            case SDL_CONTROLLER_BUTTON_DPAD_LEFT:
                                sendPipeButton("LEFT", "press",fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
                                sendPipeButton("RIGHT","press", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_DPAD_UP:
                                sendPipeButton("UP","press", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                                sendPipeButton("DOWN","press", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_A:
                                sendPipeButton("CROSS","press", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_B:
                                sendPipeButton("CIRCLE","press", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_X:
                                sendPipeButton("SQUARE","press", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_Y:
                                sendPipeButton("TRIANGLE", "press",fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_LEFTSTICK:
                                sendPipeButton("L3", "press",fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_RIGHTSTICK:
                                sendPipeButton("R3", "press",fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_START:
                                sendPipeButton("OPTIONS", "press",fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_GUIDE:
                                sendPipeButton("PS", "press",fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_LEFTSHOULDER:
                                sendPipeButton("L1", "press", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER:
                                sendPipeButton("R1", "press", fd);
                        }
                    }
                    break;
                case SDL_CONTROLLERBUTTONUP:
                    // Only process our specific controller
                    if (e.cbutton.which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controller))) {
                        std::cout << "Button Up: "
                                  << SDL_GameControllerGetStringForButton((SDL_GameControllerButton)e.cbutton.button)
                                  << std::endl;
                        switch (e.cbutton.button) {
                            case SDL_CONTROLLER_BUTTON_DPAD_LEFT:
                                sendPipeButton("LEFT","release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
                                sendPipeButton("RIGHT","release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_DPAD_UP:
                                sendPipeButton("UP","release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                                sendPipeButton("DOWN","release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_A:
                                sendPipeButton("CROSS","release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_B:
                                sendPipeButton("CIRCLE", "release",fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_X:
                                sendPipeButton("SQUARE","release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_Y:
                                sendPipeButton("TRIANGLE","release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_LEFTSTICK:
                                sendPipeButton("L3", "release",fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_RIGHTSTICK:
                                sendPipeButton("R3", "release",fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_START:
                                sendPipeButton("OPTIONS", "release",fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_GUIDE:
                                sendPipeButton("PS", "release",fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_LEFTSHOULDER:
                                sendPipeButton("L1", "release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER:
                                sendPipeButton("R1", "release", fd);
                        }
                    }
                    break;
                    // --- Handle Axis Motion (Joysticks & Triggers) ---
                case SDL_CONTROLLERAXISMOTION:
                    if (e.caxis.which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controller))) {
                        // Ignore small movements (Deadzone)
                        // if (std::abs(e.caxis.value) > JOYSTICK_DEAD_ZONE) {
                        //     std::cout << "Axis "
                        //               << SDL_GameControllerGetStringForAxis((SDL_GameControllerAxis)e.caxis.axis)
                        //               << " Value: " << (float)e.caxis.value/32768 << std::endl;
                        // }
                        switch (e.caxis.axis) {//todo R2 and L2 - works like buttons
                            case SDL_CONTROLLER_AXIS_LEFTX:
                                sendPipeAnalog("LEFT","x",(float)e.caxis.value/32768, fd);
                                if (std::abs(e.caxis.value) > JOYSTICK_DEAD_ZONE) {
                                    std::cout << "Axis "
                                              << SDL_GameControllerGetStringForAxis((SDL_GameControllerAxis)e.caxis.axis)
                                              << " Value: " << (float)e.caxis.value/32768 << std::endl;
                                }
                                break;
                            case SDL_CONTROLLER_AXIS_LEFTY:
                                sendPipeAnalog("LEFT","y",(float)e.caxis.value/32768, fd);
                                if (std::abs(e.caxis.value) > JOYSTICK_DEAD_ZONE) {
                                    std::cout << "Axis "
                                              << SDL_GameControllerGetStringForAxis((SDL_GameControllerAxis)e.caxis.axis)
                                              << " Value: " << (float)e.caxis.value/32768 << std::endl;
                                }
                                break;
                            case SDL_CONTROLLER_AXIS_RIGHTX:
                                sendPipeAnalog("RIGHT","x",(float)e.caxis.value/32768, fd);
                                break;
                            case SDL_CONTROLLER_AXIS_RIGHTY:
                                sendPipeAnalog("RIGHT","y",(float)e.caxis.value/32768, fd);
                                break;
                            case SDL_CONTROLLER_AXIS_TRIGGERRIGHT:
                                if (std::abs(e.caxis.value) > UPPER_THRESHOLD) { //todo change the seconds to mutex
                                    sendPipeButton("R2","press",fd);
                                    std::cout << "R2 VALUE = 1" << std::endl;
                                    // std::this_thread::sleep_for(std::chrono::milliseconds(10));
                                } else if (std::abs(e.caxis.value) < LOWER_THRESHOLD) {
                                    sendPipeButton("R2","release",fd);
                                    std::cout << "R2 VALUE = 0" <<  std::endl;
                                    // std::this_thread::sleep_for(std::chrono::milliseconds(40));
                                }
                                break;
                            case SDL_CONTROLLER_AXIS_TRIGGERLEFT:
                                if (std::abs(e.caxis.value) > UPPER_THRESHOLD) { //todo change the seconds to mutex
                                    sendPipeButton("L2","press",fd);
                                    std::cout << "L2 VALUE = 1" << std::endl;
                                    // std::this_thread::sleep_for(std::chrono::milliseconds(10));
                                } else if (std::abs(e.caxis.value) < LOWER_THRESHOLD) {
                                    sendPipeButton("L2","release",fd);
                                    std::cout << "L2 VALUE = 0" <<  std::endl;
                                    // std::this_thread::sleep_for(std::chrono::milliseconds(40));
                                }
                                break;
                        }

                        break;
                        // --- Hot-plugging Support ---
                        case SDL_CONTROLLERDEVICEADDED:
                        if (!controller) {
                            controller = SDL_GameControllerOpen(e.cdevice.which);
                            std::cout << "Controller attached!" << std::endl;
                        }
                        break;

                        case SDL_CONTROLLERDEVICEREMOVED:
                        if (controller && e.cdevice.which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controller))) {
                            SDL_GameControllerClose(controller);
                            controller = nullptr;
                            std::cout << "Controller disconnected!" << std::endl;
                        }
                        break;
                    }
            }
        }
    }
    SDL_Delay(10);
    std::cout << "Finished" << std::endl;
    SDL_Quit();
}