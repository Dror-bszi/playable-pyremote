#include <fstream>
#include <iostream>
#include <SDL.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <cstring>
#include <csignal>
#include <string>
#include <cmath>
#include <thread>
#include <chrono>

#define UPPER_THRESHOLD 32000
#define LOWER_THRESHOLD 200

// Global quit flag set by signal handler so the event loop exits cleanly
static volatile sig_atomic_t g_quit = 0;

static void signal_handler(int /*sig*/) {
    g_quit = 1;
}

void sendPipeButton(const std::string& button, const std::string& pressOrRelease, int pipeID) {
    std::string message = button + "\n" + pressOrRelease + "\n\n";
    if (write(pipeID, message.c_str(), message.size()) == -1 && errno != EAGAIN) {
        std::cerr << "Pipe write error: " << strerror(errno) << std::endl;
    }
}

void sendPipeAnalog(const std::string& stick, const std::string& axis, float value, int pipeID) {
    std::string message = stick + "\n" + axis + "\n" + std::to_string(value) + "\n";
    if (write(pipeID, message.c_str(), message.size()) == -1 && errno != EAGAIN) {
        std::cerr << "Pipe write error: " << strerror(errno) << std::endl;
    }
}

// Deadzone to prevent drift from slight stick movements
const int JOYSTICK_DEAD_ZONE = 8000;

// Send neutral (zero) values for all axes — used on disconnect and as a
// keep-alive heartbeat to prevent PS5 latching a stale non-zero state.
void sendNeutralAxes(int fd) {
    sendPipeAnalog("LEFT",  "x", 0.0f, fd);
    sendPipeAnalog("LEFT",  "y", 0.0f, fd);
    sendPipeAnalog("RIGHT", "x", 0.0f, fd);
    sendPipeAnalog("RIGHT", "y", 0.0f, fd);
}

int main() {

    // Register signal handlers so SIGTERM/SIGINT exit the event loop cleanly
    signal(SIGINT,  signal_handler);
    signal(SIGTERM, signal_handler);

    SDL_Event e;

    if (SDL_Init(SDL_INIT_GAMECONTROLLER | SDL_INIT_SENSOR) < 0) {
        std::cerr << "SDL could not initialize! SDL Error: " << SDL_GetError() << std::endl;
        return -1;
    }

    SDL_GameController* controller = nullptr;

    // Check for attached controllers
    if (SDL_NumJoysticks() < 1) {
        std::cout << "Warning: No joysticks connected!" << std::endl;
    } else {
        for (int i = 0; i < SDL_NumJoysticks(); ++i) {
            if (SDL_IsGameController(i)) {
                controller = SDL_GameControllerOpen(i);
                if (controller) {
                    std::cout << "Controller connected: " << SDL_GameControllerName(controller) << std::endl;

                    // Enable Gyroscope and Accelerometer for DualSense
                    SDL_GameControllerSetSensorEnabled(controller, SDL_SENSOR_GYRO, SDL_TRUE);
                    SDL_GameControllerSetSensorEnabled(controller, SDL_SENSOR_ACCEL, SDL_TRUE);

                    // Set LED Color to Purple (R:255, G:0, B:255)
                    SDL_GameControllerSetLED(controller, 255, 0, 255);
                    break;
                } else {
                    std::cerr << "Could not open game controller " << i << ": " << SDL_GetError() << std::endl;
                }
            }
        }
    }

    // OPEN PIPE — use O_NONBLOCK so we do not deadlock waiting for a reader.
    // Retry every 500ms until a reader (pyremoteplay) opens the other end.
    // Also check g_quit so a signal during startup exits cleanly.
    const char* pipe_path = "/tmp/my_pipe";
    int fd = -1;
    std::cout << "Waiting for pipe reader..." << std::endl;
    while (fd == -1 && !g_quit) {
        fd = open(pipe_path, O_WRONLY | O_NONBLOCK);
        if (fd == -1) {
            if (errno == ENXIO) {
                // No reader on the other end yet — wait and retry
                std::this_thread::sleep_for(std::chrono::milliseconds(500));
            } else {
                std::cerr << "Failed to open pipe: " << strerror(errno) << std::endl;
                SDL_Quit();
                return 1;
            }
        }
    }

    if (g_quit) {
        SDL_Quit();
        return 0;
    }

    std::cout << "Pipe opened. Listening for controller input..." << std::endl;

    // Heartbeat: if no pipe write has occurred in HEARTBEAT_MS, send neutral axes.
    // This prevents the PS5 latching a stale non-zero stick value when the DualSense
    // BT HID report rate drops (power-save / sniff mode).
    const int HEARTBEAT_MS = 200;
    using Clock = std::chrono::steady_clock;
    auto last_write_time = Clock::now();

    while (!g_quit) {
        while (SDL_PollEvent(&e) != 0) {

            switch (e.type) {
                // --- Handle Button Presses ---
                case SDL_CONTROLLERBUTTONDOWN:
                    // Only process our specific controller
                    if (e.cbutton.which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controller))) {
                        std::cout << "Button Down: "
                                  << SDL_GameControllerGetStringForButton((SDL_GameControllerButton)e.cbutton.button)
                                  << std::endl;

                        switch (e.cbutton.button) {
                            case SDL_CONTROLLER_BUTTON_DPAD_LEFT:
                                sendPipeButton("LEFT", "press", fd);
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
                                sendPipeButton("TRIANGLE", "press", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_LEFTSTICK:
                                sendPipeButton("L3", "press", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_RIGHTSTICK:
                                sendPipeButton("R3", "press", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_START:
                                sendPipeButton("OPTIONS", "press", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_GUIDE:
                                sendPipeButton("PS", "press", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_LEFTSHOULDER:
                                sendPipeButton("L1", "press", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER:
                                sendPipeButton("R1", "press", fd);
                        }
                        last_write_time = Clock::now();
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
                                sendPipeButton("CIRCLE", "release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_X:
                                sendPipeButton("SQUARE","release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_Y:
                                sendPipeButton("TRIANGLE","release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_LEFTSTICK:
                                sendPipeButton("L3", "release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_RIGHTSTICK:
                                sendPipeButton("R3", "release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_START:
                                sendPipeButton("OPTIONS", "release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_GUIDE:
                                sendPipeButton("PS", "release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_LEFTSHOULDER:
                                sendPipeButton("L1", "release", fd);
                                break;
                            case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER:
                                sendPipeButton("R1", "release", fd);
                        }
                        last_write_time = Clock::now();
                    }
                    break;
                    // --- Handle Axis Motion (Joysticks & Triggers) ---
                case SDL_CONTROLLERAXISMOTION:
                    if (e.caxis.which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controller))) {
                        switch (e.caxis.axis) {
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
                                if (std::abs(e.caxis.value) > UPPER_THRESHOLD) {
                                    sendPipeButton("R2","press",fd);
                                    std::cout << "R2 VALUE = 1" << std::endl;
                                } else if (std::abs(e.caxis.value) < LOWER_THRESHOLD) {
                                    sendPipeButton("R2","release",fd);
                                    std::cout << "R2 VALUE = 0" <<  std::endl;
                                }
                                break;
                            case SDL_CONTROLLER_AXIS_TRIGGERLEFT:
                                if (std::abs(e.caxis.value) > UPPER_THRESHOLD) {
                                    sendPipeButton("L2","press",fd);
                                    std::cout << "L2 VALUE = 1" << std::endl;
                                } else if (std::abs(e.caxis.value) < LOWER_THRESHOLD) {
                                    sendPipeButton("L2","release",fd);
                                    std::cout << "L2 VALUE = 0" <<  std::endl;
                                }
                                break;
                        }
                        last_write_time = Clock::now();
                    }
                    break;

                // --- Hot-plugging Support ---
                case SDL_CONTROLLERDEVICEADDED:
                    if (!controller) {
                        controller = SDL_GameControllerOpen(e.cdevice.which);
                        if (controller) {
                            std::cout << "Controller attached!" << std::endl;
                            SDL_GameControllerSetLED(controller, 255, 0, 255);
                        }
                    }
                    break;

                case SDL_CONTROLLERDEVICEREMOVED:
                    if (controller && e.cdevice.which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controller))) {
                        SDL_GameControllerClose(controller);
                        controller = nullptr;
                        std::cout << "Controller disconnected! Sending neutral axes." << std::endl;
                        sendNeutralAxes(fd);
                        last_write_time = Clock::now();
                    }
                    break;
            }
        }

        // Heartbeat: if the DualSense BT HID report rate has dropped (power-save /
        // sniff mode), send neutral axes to prevent the PS5 holding a stale state.
        // This fires only when SDL has been silent for HEARTBEAT_MS — during active
        // use the timestamp is updated by every event above, so this never triggers.
        auto now = Clock::now();
        auto ms_elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            now - last_write_time).count();
        if (ms_elapsed >= HEARTBEAT_MS) {
            sendNeutralAxes(fd);
            last_write_time = now;
        }

        // 10ms sleep throttles the poll loop to ~100 Hz.
        // Prevents CPU busy-wait and reduces pipe write flood.
        SDL_Delay(10);
    }

    std::cout << "Finished" << std::endl;
    SDL_Quit();
    return 0;
}
