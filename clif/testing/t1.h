/*
 * Copyright 2017 Google Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#ifndef CLIF_TESTING_T1_H_
#define CLIF_TESTING_T1_H_

#include <memory>
#include <string>

namespace some {

inline int int_id(int x) { return x; }
inline int int_plus3(int a, int b = 0, int c = 0) { return a+b+c; }

inline std::string StdString() { return std::string("std"); }

}  // namespace some

#endif  // CLIF_TESTING_T1_H_
