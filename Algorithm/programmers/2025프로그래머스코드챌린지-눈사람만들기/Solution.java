import java.util.Arrays;
import java.util.Stack;
import java.util.Queue;
import java.util.LinkedList;

class Solution {
    public long solution(String[] grid) {
        int n = grid.length;
        int m = grid[0].length();
        int[] t1 = null;
        int[] t2 = null;
        // for (String t : grid) {
        // System.out.println(t);
        // }
        int[][] passBool = new int[n][m];

        for (int i = 0; i < n; i++) {
            for (int j = 0; j < m; j++) {
                char ch = grid[i].charAt(j);
                if (ch == 'o') {
                    if (t1 == null) {
                        t1 = new int[] { i, j };
                    } else if (t2 == null) {
                        t2 = new int[] { i, j };
                    }
                } else if (ch == '#'){
                    passBool[i][j] = -1;
                }
            }
        }
        int[][] checkQ = new int[n][m];
        int[][] checkT = new int[n][m];
        int[][] checkOne = new int[n][m];

        int[] lt1 = null;
        int[] rt1 = null;
        int[] lt2 = null;
        int[] rt2 = null;

        boolean lt1OneBool = true;
        boolean rt1OneBool = true;
        boolean lt2OneBool = true;
        boolean rt2OneBool = true;

        int max = -1;
        boolean init = true;
        Queue<int[]> queue = new LinkedList<>();
        queue.add(t1);
        while (!queue.isEmpty()) {
            int[] t = queue.poll();
            int x = t[0];
            int y = t[1];
            int checkCnt = checkQ[x][y] + 1;
            checkQ[x][y] = checkCnt;
            passBool[x][y] = 1;

            if (t1[0] == x && t1[1] == y) {
                checkT[x][y] = 1;
            } else if (t2[0] == x && t2[1] == y) {
                checkT[x][y] = 2;
            }
            int checkTVal = checkT[x][y];

            boolean mxBool = false;
            boolean pxBool = false;
            boolean myBool = false;
            boolean pyBool = false;

            int mx = x - 1;
            int px = x + 1;
            int my = y - 1;
            int py = y + 1;

            int chg = 0;
            max++;
            if (x > 0) {
                char ch = grid[mx].charAt(y);
                if (checkQ[mx][y] == 0 && ch != '#') {
                    queue.add(new int[] { mx, y });
                    checkQ[mx][y] = checkCnt;
                    checkT[mx][y] = checkTVal;
                    mxBool = true;
                    chg++;
                }
            }
            if (x < n - 1) {
                char ch = grid[px].charAt(y);
                if (checkQ[px][y] == 0 && ch != '#') {
                    queue.add(new int[] { px, y });
                    checkQ[px][y] = checkCnt;
                    checkT[px][y] = checkTVal;
                    pxBool = true;
                    chg++;
                }
            }
            if (y > 0) {
                char ch = grid[x].charAt(my);
                if (checkQ[x][my] == 0 && ch != '#') {
                    queue.add(new int[] { x, my });
                    checkQ[x][my] = checkCnt;
                    checkT[x][my] = checkTVal;                                       myBool = true;
                    chg++;
                }
            }
            if (y < m - 1) {
                char ch = grid[x].charAt(py);
                if (checkQ[x][py] == 0 && ch != '#') {
                    queue.add(new int[] { x, py });
                    checkQ[x][py] = checkCnt;
                    checkT[x][py] = checkTVal;
                    pyBool = true;
                    chg++;
                }
            }

            if((init && chg < 3) || (t2[0] == x && t2[1] == y)){
                checkOne[x][y] = 1;
            } else if(chg > checkOne[x][y]) {
                checkOne[x][y] = chg;       
            }
            if(mxBool){
                checkOne[mx][y] = checkOne[x][y];
            }
            if(pxBool){
                checkOne[px][y] = checkOne[x][y];
            }
            if(myBool){
                checkOne[x][my] = checkOne[x][y];
            }
            if(pyBool){
                checkOne[x][py] = checkOne[x][y];
            }

            if (init) {
                boolean chgBool = false;
                if (mx == t2[0] && y == t2[1]) {
                    lt2 = new int[] { mx, y };
                    chgBool = true;
                } else if (px == t2[0] && y == t2[1]) {
                    lt2 = new int[] { px, y };
                    chgBool = true;
                } else if (x == t2[0] && my == t2[1]) {
                    lt2 = new int[] { x, my };
                    chgBool = true;
                } else if (x == t2[0] && py == t2[1]) {
                    lt2 = new int[] { x, py };
                    chgBool = true;
                }
                if (chgBool && rt1 == null) {
                    rt1 = new int[] { x, y };
                }
                if (chg > 2) {
                    lt1 = new int[] { x, y };
                    rt1 = new int[] { x, y };
                    lt1OneBool = false;
                    rt1OneBool = false;
                } else if (chg == 1) {
                    lt1 = new int[] { x, y };
                }
            } else if (chg > 1) {
                if (checkTVal == 1) {
                    if (mx == t2[0] && y == t2[1] && mxBool) {
                        if (lt2 == null) {
                            lt2 = new int[] { mx, y };
                        }
                    } else if (px == t2[0] && y == t2[1] && pxBool) {
                        if (lt2 == null) {
                            lt2 = new int[] { px, y };
                        }
                    } else if (x == t2[0] && my == t2[1] && myBool) {
                        if (lt2 == null) {
                            lt2 = new int[] { x, my };
                        }
                    } else if (x == t2[0] && py == t2[1] && pyBool) {
                        if (lt2 == null) {
                            lt2 = new int[] { x, py };
                        }
                    }
                    if (lt1 == null) {
                        lt1 = new int[] { x, y };
                        lt1OneBool = false;
                    } else if (rt1 == null) {
                        rt1 = new int[] { x, y };
                        rt1OneBool = false;
                    }
                } else if (checkTVal == 2) {
                    if (lt2 == null) {
                        lt2 = new int[] { x, y };
                        lt2OneBool = false;
                    } else if (rt2 == null) {
                        rt2 = new int[] { x, y };
                        rt2OneBool = false;
                    }
                }
            } else if (chg == 1) {
                if (checkTVal == 1) {
                    boolean chgBool = false;
                    if (mx == t2[0] && y == t2[1] && mxBool) {
                        if (lt2 == null) {
                            lt2 = new int[] { mx, y };
                        }
                        chgBool = true;
                    } else if (px == t2[0] && y == t2[1] && pxBool) {
                        if (lt2 == null) {
                            lt2 = new int[] { px, y };
                        }
                        chgBool = true;
                    } else if (x == t2[0] && my == t2[1] && myBool) {
                        if (lt2 == null) {
                            lt2 = new int[] { x, my };
                        }
                        chgBool = true;
                    } else if (x == t2[0] && py == t2[1] && pyBool) {
                        if (lt2 == null) {
                            lt2 = new int[] { x, py };
                        }
                        chgBool = true;
                    }
                    if (chgBool) {
                        if (rt1 == null) {
                            rt1 = new int[] { x, y };
                        }
                    }
                }
            } else {
                int tOneCnt = 0;

               if (lt1OneBool) {
                    tOneCnt++;
               }
               if (rt1OneBool) {
                    tOneCnt++;
               } 
               if (lt2OneBool) {
                    tOneCnt++;
                }
                if (rt2OneBool) {
                    tOneCnt++;
                }
                if (tOneCnt > 2 && checkOne[x][y] == 1) {
                    int conCnt = 0;
                    if (x > 0) {
                        if (checkQ[mx][y] > 0) {
                            conCnt++;
                        }
                    }
                    if (x < n - 1) {
                        if (checkQ[px][y] > 0) {
                            conCnt++;
                        }
                    }
                    if (y > 0) {
                        if (checkQ[x][my] > 0) {
                            conCnt++;
                        }
                    }
                    if (y < m - 1) {
                        if (checkQ[x][py] > 0) {
                            conCnt++;
                        }
                    }
                    if (conCnt > 1) {
                        lt1OneBool = false;
                        rt1OneBool = false;
                        lt2OneBool = false;
                        rt2OneBool = false;
                    }
                }
                if (checkTVal == 1 && checkOne[x][y] == 1) {
                    if (lt1 == null) {
                        lt1 = new int[] { x, y };
                    } else if (rt1 == null) {
                        rt1 = new int[] { x, y };
                    }
                } else if (checkTVal == 2 && checkOne[x][y] == 1) {
                    if (lt2 == null) {
                        lt2 = new int[] { x, y };
                    } else if (rt2 == null) {
                        rt2 = new int[] { x, y };
                    }
                    if (x > 0) {
                        if (checkOne[mx][y] > 1) {
                            lt2OneBool = false;
                        }
                    }
                    if (x < n - 1) {
                        if (checkOne[px][y] > 1) {
                            lt2OneBool = false;
                        }
                    }
                    if (y > 0) {
                        if (checkOne[x][my] > 1) {
                            lt2OneBool = false;
                        }
                    }
                    if (y < m - 1) {
                        if (checkOne[x][py] > 1) {
                            lt2OneBool = false;
                        }
                    }
                }
            }
            init = false;
        }


        int tOneCnt = 0;

        if (lt1OneBool) {
            tOneCnt++;
        }
        if (rt1OneBool) {
            tOneCnt++;
        }
        if (lt2OneBool) {
            tOneCnt++;
        }
        if (rt2OneBool) {
            tOneCnt++;
        }



        int dist = checkQ[t2[0]][t2[1]] - checkQ[t1[0]][t1[1]];
        long answer = 0;

        if (tOneCnt == 4) {
            int t1d = Math.abs(checkQ[lt1[0]][lt1[1]] - checkQ[t1[0]][t1[1]])
                    + Math.abs(checkQ[rt1[0]][rt1[1]] - checkQ[t1[0]][t1[1]]) - dist + 2;
            int rt2d = Math.abs(checkQ[lt2[0]][lt2[1]] - checkQ[rt2[0]][rt2[1]]) + 1;
            int rtdMin = Math.min(t1d, rt2d);
            int t1f = t1d + dist - 1;
            int t2f = rt2d + dist - 1;
            int tfMin = Math.min(t1f, t2f);
            int a = rtdMin;
            max = max - rtdMin + 1;
            int b = max + a;
            for (int i = max; i >= 1; i--) {
                int c = b - i;
                if (c > tfMin) {
                    c = tfMin;
                }
                if (c > i) {
                    c = i;
                }                for (int j = c; j >= 1; j--) {
                    if (dist < i + j) {
                        answer = answer + 1;
                    } else {
                        break;
                    }
                }
            }
        } else if (tOneCnt == 3) {
            int pCnt = 0;
            int bCnt = 0;
            if(lt1OneBool && rt1OneBool){
               pCnt = 1;
               bCnt = 1;
            } else if(lt2OneBool && rt2OneBool){
               pCnt = 2 - dist;
               bCnt = dist;
            }
            int t1d = Math.abs(checkQ[lt1[0]][lt1[1]] - checkQ[t1[0]][t1[1]])
                    + Math.abs(checkQ[rt1[0]][rt1[1]] - checkQ[t1[0]][t1[1]]) + pCnt;
            int rt2d = Math.abs(checkQ[lt2[0]][lt2[1]] - checkQ[rt2[0]][rt2[1]]) + bCnt;
            int iCnt = 0;
            int jCnt = 0;
            if (!lt1OneBool) {
                iCnt = t1d;
                jCnt = rt2d;
            } else if (!rt1OneBool) {
                iCnt = t1d;
                jCnt = rt2d;
            } else if (!lt2OneBool) {
                iCnt = rt2d;
                jCnt = t1d;
            } else if (!rt2OneBool) {
                iCnt = rt2d;
                jCnt = t1d;
            }

            int a = 1;
            int b = max + a;
            for (int i = max; i >= 1; i--) {
                int c = b - i;
                if (i <= iCnt) {
                    c = jCnt;
                }
                if (c > i) {
                    c = i;
                }
                for (int j = c; j >= 1; j--) {
                    if (dist < i + j) {
                        answer = answer + 1;
                    } else {
                        break;
                    }
                }
            }
        } else {
            int b = max + 1;
            for (int i = max; i >= 1; i--) {
                int c = b - i;
                if (c > i) {
                    c = i;
                }
                for (int j = c; j >= 1; j--) {
                    if (dist < i + j) {
                        answer = answer + 1;
                    } else {
                        break;
                    }
                }
            }
        }

        return answer;
    }
}
