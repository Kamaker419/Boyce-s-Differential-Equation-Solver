from flask import Flask, request, jsonify, send_file
import sympy as sp
import re
import os
import sys
import webbrowser
from threading import Timer

# PyInstaller 빌드 경로 보정
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

@app.route('/')
def serve_index():
    return send_file(os.path.join(base_path, 'ODE.html'))

def preprocess_eq(eq_str):
    """지저분한 수식을 SymPy가 이해할 수 있는 우아한 형태로 다듬어줍니다."""
    eq_str = eq_str.replace('\\sin', 'sin').replace('\\cos', 'cos').replace('\\tan', 'tan')
    eq_str = eq_str.replace('\\exp', 'exp').replace('\\ln', 'log').replace('\\log', 'log')
    eq_str = eq_str.replace('\\left(', '(').replace('\\right)', ')')
    eq_str = eq_str.replace('\\cdot', '*').replace('\\pi', 'pi').replace('\\e', 'E')
    
    eq_str = re.sub(r'\\sqrt{([^}]+)}', r'sqrt(\1)', eq_str)
    eq_str = re.sub(r'\\frac{([^{}]+)}{([^{}]+)}', r'((\1)/(\2))', eq_str)
    eq_str = re.sub(r'\^\{([^}]+)\}', r'**(\1)', eq_str)
    eq_str = eq_str.replace('^', '**')
    
    # y의 도함수 표현 변환 (n차 방정식용)
    eq_str = eq_str.replace("y''''''", "y6").replace("y'''''", "y5").replace("y''''", "y4")
    eq_str = eq_str.replace("y'''", "y3").replace("y''", "y2").replace("y'", "y1")
    return eq_str

@app.route('/solve', methods=['POST'])
def solve_ode():
    data = request.json
    equation_str = data.get('equation_str', '')
    x0_str = data.get('x0_str', '0')
    calc_series = data.get('calc_series', True)
    
    eq_str = preprocess_eq(equation_str)
    
    x = sp.Symbol('x')
    y = sp.Function('y')(x)
    
    local_dict = {'y': y, 'x': x}
    for i in range(1, 7):
        local_dict[f"y{i}"] = y.diff(x, i)
        
    result = {"exact": "", "series": "", "radius": "", "error": None}
    
    try:
        x0 = sp.sympify(x0_str)
    except Exception:
        x0 = 0

    try:
        eq = sp.sympify(eq_str, locals=local_dict)
        ode = sp.Eq(eq, 0)
    except Exception as e:
        result["error"] = "어머, 수식을 이해하지 못했어요. 올바르게 입력한 게 맞나요?"
        return jsonify(result)

    exact_solution = None
    try:
        exact_solution = sp.dsolve(ode, y)
        result["exact"] = sp.latex(exact_solution)
    except Exception:
        result["exact"] = "\\text{닫힌 형태의 일반해를 찾을 수 없네요.}"

    try:
        order = sp.ode_order(ode, y)
    except Exception:
        order = 1

    if not calc_series:
        result["series"] = "\\text{급수해 탐색 마법이 꺼져 있습니다.}"
        result["radius"] = "\\text{탐색 오프}"
    elif order > 2:
        result["series"] = f"\\text{{{order}차 방정식이군요. 급수해는 우아하게 2차까지만 제공합니다.}}"
        result["radius"] = "\\text{계산 생략}"
    else:
        series_sol = None
        subs_dict = {y: 0}
        for i in range(1, 7):
            subs_dict[local_dict[f"y{i}"]] = 0
        g_x = eq.subs(subs_dict)
        homo_eq = eq - g_x
        homo_ode = sp.Eq(homo_eq, 0)

        hints = ['1st_power_series_ordinary'] if order == 1 else ['2nd_power_series_ordinary', '2nd_power_series_regular']
        
        for h in hints:
            try:
                series_sol = sp.dsolve(homo_ode, y, hint=h, n=8, x0=x0)
                if series_sol is not None:
                    break
            except Exception:
                continue

        if series_sol is None:
            try:
                homo_exact = sp.dsolve(homo_ode, y)
                if homo_exact is not None:
                    expanded = homo_exact.rhs.series(x, x0, 8).removeO()
                    series_sol = sp.Eq(y, expanded)
            except Exception:
                pass

        if series_sol is not None:
            rhs = series_sol.rhs.removeO()
            C1, C2 = sp.symbols('C1 C2')
            
            if x0 == 0:
                rhs_expanded = sp.expand(rhs)
                y1 = rhs_expanded.coeff(C1)
                y2 = rhs_expanded.coeff(C2)
            else:
                t = sp.Symbol('t')
                rhs_t = rhs.subs(x, t + x0)
                rhs_t_expanded = sp.expand(rhs_t)
                y1_t = rhs_t_expanded.coeff(C1)
                y2_t = rhs_t_expanded.coeff(C2)
                
                if x0.is_number and x0 < 0:
                    symbol_name = f"\\left(x + {sp.latex(-x0)}\\right)"
                else:
                    symbol_name = f"\\left(x - {sp.latex(x0)}\\right)"
                    
                X_poly = sp.Symbol(symbol_name)
                y1 = y1_t.subs(t, X_poly)
                y2 = y2_t.subs(t, X_poly)
            
            if order == 2 and (y1 != 0 or y2 != 0):
                latex_str = f"\\begin{{aligned}} y_1(x) &= {sp.latex(y1)} \\\\"
                latex_str += f" y_2(x) &= {sp.latex(y2)} \\end{{aligned}}"
                result["series"] = latex_str
            elif order == 1 and y1 != 0:
                latex_str = f"y_1(x) = {sp.latex(y1)}"
                result["series"] = latex_str
            else:
                if x0 == 0:
                    result["series"] = sp.latex(sp.Eq(y, rhs))
                else:
                    t = sp.Symbol('t')
                    rhs_t = rhs.subs(x, t + x0)
                    if x0.is_number and x0 < 0:
                        symbol_name = f"\\left(x + {sp.latex(-x0)}\\right)"
                    else:
                        symbol_name = f"\\left(x - {sp.latex(x0)}\\right)"
                    X_poly = sp.Symbol(symbol_name)
                    result["series"] = sp.latex(sp.Eq(y, sp.expand(rhs_t).subs(t, X_poly)))
        else:
            result["series"] = "\\text{어머, 제차 방정식조차 특이성이 너무 강해 급수해 탐색에 실패했습니다.}"

        try:
            highest_deriv = None
            for i in range(2, 0, -1):
                if local_dict[f"y{i}"] in eq.free_symbols or eq.has(local_dict[f"y{i}"]):
                    highest_deriv = local_dict[f"y{i}"]
                    break
                    
            if highest_deriv:
                coeff_dict = eq.collect(highest_deriv, evaluate=False)
                if highest_deriv in coeff_dict:
                    p_x = coeff_dict[highest_deriv]
                    if p_x.is_constant():
                        result["radius"] = "\\infty"
                    else:
                        singularities = sp.solve(p_x, x)
                        if not singularities:
                            result["radius"] = "\\infty"
                        else:
                            min_distance = sp.oo
                            for sing in singularities:
                                if sing != x0:
                                    dist = sp.Abs(sing - x0)
                                    if dist < min_distance:
                                        min_distance = dist
                            if min_distance == sp.oo:
                                result["radius"] = "\\infty"
                            else:
                                result["radius"] = sp.latex(min_distance)
                else:
                    result["radius"] = "\\text{N/A}"
            else:
                result["radius"] = "\\text{N/A}"
        except Exception:
            result["radius"] = "\\text{계산 불가}"

    return jsonify(result)

@app.route('/laplace', methods=['POST'])
def laplace_transform():
    data = request.json
    eq_str = data.get('equation_str', '')
    direction = data.get('direction', 'forward')
    
    # 1차 전처리: 흉측한 LaTeX 찌꺼기들을 정리합니다.
    eq_str = preprocess_eq(eq_str)
    
    t = sp.Symbol('t', real=True, positive=True)
    s = sp.Symbol('s')
    
    try:
        # 마녀의 섬세한 2차 전처리: sympy가 t와 s를 헷갈리지 않도록 명시적으로 주입합니다.
        eq = sp.sympify(eq_str, locals={'t': t, 's': s})
        
        if direction == 'inverse':
            # F(s)를 f(t)로 역변환
            sol = sp.inverse_laplace_transform(eq, s, t)
            result_latex = f"f(t) = {sp.latex(sol)}"
        else:
            # f(t)를 F(s)로 라플라스 변환
            sol = sp.laplace_transform(eq, t, s, noconds=True)
            result_latex = f"F(s) = {sp.latex(sol)}"
            
        return jsonify({'result': result_latex})
    except Exception as e:
        return jsonify({'error': '변환에 실패했습니다. 수식이 너무 흉측한 건 아닐까요?'})

@app.route('/solve_system', methods=['POST'])
def solve_system():
    data = request.json
    eqs_str = data.get('equations', [])
    
    t = sp.Symbol('t')
    funcs = [sp.Function(f'y{i+1}')(t) for i in range(len(eqs_str))]
    
    # 여기서 마녀의 우아한 마법이 들어갑니다. x를 치든 t를 치든 동일하게 취급하도록 강제합니다.
    local_dict = {'t': t, 'x': t} 
    for i, f in enumerate(funcs):
        local_dict[f'y{i+1}'] = f
        
    odes = []
    try:
        for i, eq_str in enumerate(eqs_str):
            parsed_str = preprocess_eq(eq_str)
            eq = sp.sympify(parsed_str, locals=local_dict)
            odes.append(sp.Eq(funcs[i].diff(t), eq))
            
        sols = sp.dsolve(odes)
        
        if isinstance(sols, list) or isinstance(sols, tuple) or isinstance(sols, set):
            latex_res = "\\begin{aligned} " + " \\\\ ".join([sp.latex(s) for s in sols]) + " \\end{aligned}"
        else:
            latex_res = sp.latex(sols)
            
        return jsonify({'result': latex_res})
    except Exception as e:
        return jsonify({'error': f"연립방정식 해석 실패: {str(e)}"})

def open_browser():
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == '__main__':
    Timer(1, open_browser).start()
    app.run(host='127.0.0.1', port=5000)