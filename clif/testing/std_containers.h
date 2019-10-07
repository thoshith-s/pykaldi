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
#ifndef CLIF_TESTING_STD_CONTAINERS_H_
#define CLIF_TESTING_STD_CONTAINERS_H_

#include <unordered_map>
#include <utility>
#include <vector>

// list input arg and return value.
inline std::vector<int> Mul(std::vector<int> v, int m) {
  for (auto& i : v) { i *= m; }
  return v;
}

inline std::vector<bool> Even(const std::vector<int>& v) {
  std::vector<bool> e(v.size());
  for (int i=0; i < v.size(); ++i) { if ((v[i] & 1) == 0) { e[i] = true; }}
  return e;
}

inline std::vector<bool>* Odd(const std::vector<int>& v) {
  std::vector<bool>* e = new std::vector<bool>(v.size());
  for (int i=0; i < v.size(); ++i) { if (v[i] & 1) { (*e)[i] = true; }}
  return e;
}

// dict input arg.
inline bool Find(int val, std::unordered_map<int, int> m, int* key) {
  for (const auto& i : m)
    if (i.second == val) {
      if (key) *key = i.first;
      return true;
  }
  return false;
}

// list of lists return value.
inline std::vector<std::vector<int>> Ones(int r, int c) {
  std::vector<std::vector<int>> rows;
  for (int i = 0; i < r; ++i) {
    std::vector<int> columns(c, 1);
    rows.emplace_back(columns);
  }
  return rows;
}

// list of tuples return value
inline std::vector<std::pair<string, string>> Capitals() {
  std::vector<std::pair<string, string>> capitals;
  capitals.push_back(std::pair<string, string>("CA", "Sacramento"));
  capitals.push_back(std::pair<string, string>("OR", "Salem"));
  capitals.push_back(std::pair<string, string>("WA", "Olympia"));
  return capitals;
}

// list of lists input args and return value.
inline std::vector<std::vector<int>> MatrixSum(
    std::vector<std::vector<int>> a, std::vector<std::vector<int>> b) {
  std::vector<std::vector<int>> sum;
  for (size_t i = 0; i < a.size(); ++i) {
    sum.emplace_back(std::vector<int>(a[i].size()));
    for (size_t j = 0; j < a[i].size(); ++j) {
      sum[i][j] = a[i][j] + b[i][j];
    }
  }
  return sum;
}

inline std::tuple<std::tuple<int, int, int>, std::tuple<int, int, int>>
Make2By3() {
  return std::tuple<std::tuple<int, int, int>, std::tuple<int, int, int>>();
}

inline std::tuple<int, int, int, int, int, int> Flatten2By3(
const std::tuple<std::tuple<int, int, int>, std::tuple<int, int, int>>& m) {
  return std::make_tuple(std::get<0>(std::get<0>(m)),
                         std::get<1>(std::get<0>(m)),
                         std::get<2>(std::get<0>(m)),
                         std::get<0>(std::get<1>(m)),
                         std::get<1>(std::get<1>(m)),
                         std::get<2>(std::get<1>(m)));
}

#endif  // CLIF_TESTING_STD_CONTAINERS_H_
