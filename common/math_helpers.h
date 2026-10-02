#ifndef VITA_LAB_MATH_H
#define VITA_LAB_MATH_H
float clampf(float value,float low,float high);
float axis_raw(unsigned char raw);
float axis_deadzone(unsigned char raw,float deadzone);
float normalize_touch(int coordinate,int minimum,int maximum);
#endif
