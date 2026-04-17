RESULT_TMPL = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {
            margin: 0;
            padding: 80px 0;
            /* Premium gorgeous gradient background */
            background-color: #fff0eb;
            background-image: 
                radial-gradient(at 0% 0%, hsla(28,100%,74%,0.8) 0, transparent 50%), 
                radial-gradient(at 50% 0%, hsla(340,100%,76%,0.8) 0, transparent 50%), 
                radial-gradient(at 100% 0%, hsla(22,100%,77%,0.8) 0, transparent 50%),
                radial-gradient(at 50% 100%, hsla(340,100%,76%,0.4) 0, transparent 50%);
            font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            box-sizing: border-box;
        }
        .card {
            width: 94%;
            max-width: 1200px;
            background: rgba(255, 255, 255, 0.85);
            /* Astrbot playwright may or may not support backdrop-filter based on OS, but we include it */
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-radius: 40px;
            box-shadow: 0 30px 60px rgba(238, 91, 43, 0.15),
                        inset 0 2px 0 0 rgba(255, 255, 255, 1);
            padding: 80px;
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            align-items: center;
            position: relative;
        }
        
        .header-badge {
            background: linear-gradient(135deg, #ff6a00, #ee0979);
            color: white;
            padding: 10px 24px;
            border-radius: 50px;
            font-size: 20px;
            font-weight: 600;
            letter-spacing: 2px;
            text-transform: uppercase;
            margin-bottom: 30px;
            box-shadow: 0 10px 20px rgba(238, 9, 121, 0.3);
        }

        .title {
            color: #4a4a4a;
            font-size: 42px;
            font-weight: 700;
            margin-bottom: 20px;
            text-align: center;
            line-height: 1.6;
        }

        .user-name {
            color: #ee0979;
            font-weight: bold;
        }

        .divider {
            width: 60px;
            height: 8px;
            background: linear-gradient(90deg, #ff6a00, #ee0979);
            border-radius: 4px;
            margin: 20px 0 40px 0;
        }

        .cat-name {
            font-size: 88px;
            margin: 0 0 40px 0;
            font-weight: 900;
            text-align: center;
            /* Gradient text */
            background: linear-gradient(to right, #ff416c, #ff4b2b);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            line-height: 1.15;
            padding: 10px;
        }

        .comment-box {
            background: rgba(255, 255, 255, 0.6);
            border: 2px solid rgba(255, 255, 255, 0.8);
            border-radius: 24px;
            padding: 40px;
            width: 100%;
            box-sizing: border-box;
            box-shadow: 0 10px 30px rgba(0,0,0,0.03);
        }

        .comment {
            font-size: 36px;
            color: #333;
            line-height: 1.8;
            text-align: justify;
            white-space: pre-wrap;
            word-wrap: break-word;
            font-weight: 500;
        }

        .footer {
            margin-top: 30px;
            color: #aaa;
            font-size: 26px;
            font-weight: 500;
            text-align: center;
            white-space: pre-wrap;
            line-height: 1.6;
        }

        .test-id-box {
            margin-top: 10px;
            color: #fff;
            font-size: 72px;
            font-weight: 900;
            background: linear-gradient(135deg, #ff6a00, #ee0979);
            padding: 30px 60px;
            border-radius: 40px;
            box-shadow: 0 20px 40px rgba(238, 9, 121, 0.3);
            text-align: center;
            letter-spacing: 4px;
            margin-bottom: 40px;
        }

        .invite-tip {
            color: #555;
            font-size: 36px;
            font-weight: 500;
            background: rgba(0,0,0,0.05);
            padding: 20px 40px;
            border-radius: 20px;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="title"><span class="user-name">{{ user_name }}</span> 的<br>{{ quiz_title }} 测试结果</div>
        
        <div class="divider"></div>
        
        <div class="cat-name">{{ cat_name }}</div>
        
        <div class="comment-box">
            <div class="comment">{{ ai_comment }}</div>
        </div>
        <div class="test-id-box">#quiz {{ display_id }}</div>
        <div class="invite-tip">{{ invite_tip_text }}</div>
        <div class="footer">{{ footer_text }}</div>
    </div>
</body>
</html>
"""

INVITE_TMPL = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {
            margin: 0;
            padding: 80px 0;
            background-color: #f8fbff;
            background-image: 
                radial-gradient(at 0% 0%, hsla(210,100%,74%,0.8) 0, transparent 50%), 
                radial-gradient(at 50% 0%, hsla(180,100%,76%,0.8) 0, transparent 50%), 
                radial-gradient(at 100% 0%, hsla(200,100%,77%,0.8) 0, transparent 50%);
            font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            box-sizing: border-box;
        }
        .card {
            width: 94%;
            max-width: 1200px;
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-radius: 40px;
            box-shadow: 0 30px 60px rgba(0, 118, 255, 0.15),
                        inset 0 2px 0 0 rgba(255, 255, 255, 1);
            padding: 80px;
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            align-items: center;
            position: relative;
        }
        
        .header-badge {
            background: linear-gradient(135deg, #0076ff, #00b4db);
            color: white;
            padding: 12px 30px;
            border-radius: 50px;
            font-size: 24px;
            font-weight: 600;
            letter-spacing: 2px;
            margin-bottom: 40px;
            box-shadow: 0 10px 20px rgba(0, 118, 255, 0.3);
        }

        .title {
            color: #333;
            font-size: 56px;
            font-weight: 800;
            margin-bottom: 20px;
            text-align: center;
            line-height: 1.4;
            background: linear-gradient(to right, #0052d4, #4364f7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .subtitle {
            color: #666;
            font-size: 32px;
            font-weight: 500;
            margin-bottom: 30px;
        }

        .desc-box {
            color: #555;
            font-size: 28px;
            font-weight: 400;
            margin-bottom: 40px;
            text-align: center;
            line-height: 1.6;
            max-width: 90%;
            background: rgba(0, 118, 255, 0.05);
            padding: 20px 40px;
            border-radius: 20px;
            border-left: 6px solid #0076ff;
        }

        .test-id-box {
            margin-top: 10px;
            color: #fff;
            font-size: 72px;
            font-weight: 900;
            background: linear-gradient(135deg, #ff6a00, #ee0979);
            padding: 30px 60px;
            border-radius: 40px;
            box-shadow: 0 20px 40px rgba(238, 9, 121, 0.3);
            text-align: center;
            letter-spacing: 4px;
            margin-bottom: 40px;
        }

        .invite-tip {
            color: #555;
            font-size: 36px;
            font-weight: 500;
            background: rgba(0,0,0,0.05);
            padding: 20px 40px;
            border-radius: 20px;
            text-align: center;
        }

        .footer {
            margin-top: 60px;
            color: #aaa;
            font-size: 26px;
            text-align: center;
            white-space: pre-wrap;
            line-height: 1.6;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="header-badge">🆕 全新测试发布</div>
        <div class="title">{{ quiz_title }}</div>
        <div class="subtitle">共包含 {{ q_count }} 道题目 · 作者: <span style="color:#0076ff; font-weight:bold;">{{ author_name }}</span></div>
        <div class="desc-box">{{ quiz_desc }}</div>
        
        <div class="test-id-box">#quiz {{ display_id }}</div>
        <div class="invite-tip">{{ invite_tip_text }}</div>
        
        <div class="footer">{{ footer_text }}</div>
    </div>
</body>
</html>
"""
