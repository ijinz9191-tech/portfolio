import java.util.*;
import java.util.stream.IntStream;

class Solution {
   public long[] solution(int[] values, int[][] edges, int[][] queries) {
         // 초기 셋팅
        int n = values.length;
        long[] subTreeSum = new long[n];
        int[] parents = new int[n];
        int[][] cpEdges = Arrays.copyOf(edges, n - 1);
        Arrays.fill(parents, -1);

        edges = null;

        // 부모자식 셋팅
        Arrays.sort(cpEdges, (a, b) -> {
            int a1 = a[0];
            int a2 = a[1];
            int b1 = b[0];
            int b2 = b[1];
            int c = a1 < a2 ? a1 : a2;
            int d = b1 < b2 ? b1 : b2;
            return Integer.compare(c, d);
        });

        ArrayList<Integer>[] childNode = new ArrayList[n];
        String[] sv = new String[n];
        Stack<Integer> stack = new Stack<>();
        stack.push(0);
        while (!stack.isEmpty()) {
            int idx = stack.pop();
            if (idx > 0) {
                if (sv[idx] != null) {
                    String[] strIdxList = sv[idx].split(",");
                    for (String strIdx : strIdxList) {
                        int i = Integer.parseInt(strIdx);
                        if (parents[i] == -1 && i != 0) {
                            parents[i] = idx;
                            if (childNode[idx] == null) {
                                childNode[idx] = new ArrayList<>();
                            }
                            childNode[idx].add(i);
                            stack.push(i);
                        }
                    }
                }
            } else {
                for (int[] edge : cpEdges) {
                    int v1 = edge[0] - 1;
                    int v2 = edge[1] - 1;
                    if (v1 == idx && parents[v2] == -1 && v2 != 0) {
                        parents[v2] = v1;
                        if (childNode[v1] == null) {
                            childNode[v1] = new ArrayList<>();
                        }
                        childNode[v1].add(v2);
                        stack.push(v2);
                    } else if (v2 == idx && parents[v1] == -1 && v1 != 0) {
                        parents[v1] = v2;
                        if (childNode[v2] == null) {
                            childNode[v2] = new ArrayList<>();
                        }
                        childNode[v2].add(v1);
                        stack.push(v1);
                    } else {
                        sv[v1] = ((sv[v1] == null) ? "" : sv[v1] + ",") + v2;
                        sv[v2] = ((sv[v2] == null) ? "" : sv[v2] + ",") + v1;
                    }
                }
            }
        }

        sv = null;
        cpEdges = null;

        Stack<Boolean> visited = new Stack<>();

        stack.push(0);
        visited.push(false);

        int[] order = new int[n];
        int i = 0;

        while (!stack.isEmpty()) {
            int idx = stack.peek();
            boolean currVisited = visited.peek();

            if (currVisited) {
                stack.pop();
                visited.pop();
                subTreeSum[idx] += values[idx];
                if (childNode[idx] != null) {
                    for (int child : childNode[idx]) {
                        subTreeSum[idx] += subTreeSum[child];
                    }
                }
            } else {
                order[i] = idx;
                i++;
                visited.pop();
                visited.push(true);
                if (childNode[idx] != null) {
                    for (int child : childNode[idx]) {
                        stack.push(child);
                        visited.push(false);
                    }
                }
            }
        }

        visited = null;
        stack = null;
        childNode = null;

        int[] rOrder = new int[n];

        i = 0;
        for (int t : order) {
            rOrder[t] = i;
            i++;
        }

        int[] cpValues = new int[n];
        int[] cpParents = new int[n];
        long[] cpSubTreeSum = new long[n];

        for (i = 0; i < n; i++) {
            cpValues[i] = values[order[i]];
            cpSubTreeSum[i] = subTreeSum[order[i]];
            if (parents[i] != -1) {
                cpParents[i] = rOrder[parents[order[i]]];
            } else {
                cpParents[i] = -1;
            }
        }

        values = null;
        subTreeSum = null;
        parents = null;
        order = null;

        long[] answer = new long[oneQuery(queries)];
        int answerIdx = 0;
        for (int[] query : queries) {
            int u = rOrder[query[0] - 1];
            int w = query[1];
            if (w == -1) {
                answer[answerIdx++] = cpSubTreeSum[u];
            } else {
                int cpInt = cpValues[u];
                if (u == 0) {
                    cpSubTreeSum[0] -= cpValues[0];
                    cpValues[0] = w;
                    cpSubTreeSum[0] += cpValues[0];
                    continue;
                }
                while (u != 0) {
                    int parentIdx = cpParents[u];
                    int parentVal = cpValues[parentIdx];
                    cpSubTreeSum[u] += (parentVal - cpInt);
                    cpValues[u] = parentVal;
                    u = parentIdx;
                }
                cpSubTreeSum[0] -= cpInt;
                cpValues[0] = w;
                cpSubTreeSum[0] += cpValues[0];
            }
        }
        return answer;
    }


    private int oneQuery(int[][] queries) {
        int cnt = 0;
        for (int[] i : queries) {
            if (i[1] == -1)
                cnt++;
        }
        return cnt;
    }
}
