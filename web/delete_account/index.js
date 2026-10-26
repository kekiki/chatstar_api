var passwordShow = false;
var requestUrl = 'http://172.18.188.141:8000/api/user/deleteAccountWithAccountPassword';

function toggleDeleteButton(input) {
    var deleteButton = document.querySelector('#account_input img');
    if (input.value) {
        deleteButton.style.display = 'block';
    } else {
        deleteButton.style.display = 'none';
    }
}

function deleteInput(button) {
    var input = button.previousElementSibling;
    input.value = '';
    button.style.display = 'none';
}
function onTogglePasswordShow(img) {
    var input = document.querySelector('#password_input input');
    if (passwordShow) {
        img.setAttribute('src', 'assets/eye_off.png');
        input.setAttribute('type', 'password');
    } else {
        img.setAttribute('src', 'assets/eye_on.png');
        input.setAttribute('type', 'text');
    }
    passwordShow = !passwordShow;
}
function onSubmit() {

    var password = document.querySelector('#password_input input').value;
    var username = document.querySelector('#account_input input').value;
    if (username == '') {
        alert('Please enter your account')
        return;
    }
    if (password == '') {
        alert('Please enter you password')
        return;
    }
    if (confirm('Please confirm your operation, your account will be destroyed immediately after cancellation!') == false) {
        return;
    }

    // 密码进行md5加密
    var md5Password = CryptoJS.MD5(password).toString();
    axios.post(requestUrl, {
        username: username,
        password: md5Password,
    }).then(response => {
        console.log(response);
        let data = response['data']
        if (data['code'] == 0) {
            alert('Successfully canceled account')
            document.querySelector('#password_input input').value = '';
            document.querySelector('#account_input input').value = '';
        } else {
            alert(data['message'])
        }
    }).catch(err => {
        console.log(err)
    })
}